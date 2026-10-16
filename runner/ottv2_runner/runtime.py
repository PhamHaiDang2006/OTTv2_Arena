from __future__ import annotations

import asyncio
import os
import shutil
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .archive import extract_source
from .callbacks import CallbackSender
from .config import Settings
from .engine import BuildVerifier, EngineFactory, load_build_verifier, load_engine_factory
from .registry import DockerRegistryPublisher, ImagePublisher
from .errors import BotBuildError, InfrastructureError, LeaseLost, UnsupportedLanguage
from .http import HttpTransport, UrllibTransport
from .lease import LeaseHeartbeat, RedisLease
from .outbox import CallbackOutbox, PendingCallback
from .sandbox import DockerSandbox, Sandbox
from .storage import ObjectStore, S3ObjectStore, build_log_key, game_artifacts, sha256, staging_key
from .validation import validate_build_job, validate_match_job

MAX_BUILD_LOG_BYTES = 1024 * 1024
MAX_CALLBACK_ERROR = 500
_GAME_REASONS = {
    "GOAL", "WIPEOUT", "STALEMATE", "TIMEOUT", "ILLEGAL_MOVE", "CRASH", "MOVE_LIMIT",
}


class HeartbeatReporter:
    def __init__(self, settings: Settings, transport: HttpTransport, kind: str):
        self.settings = settings
        self.transport = transport
        self.kind = kind
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="runner-api-heartbeat", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.wait(30):
            payload = {
                "worker_id": self.settings.worker_id,
                "kind": self.kind,
                "job_id": None,
                "sent_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            }
            try:
                self.transport.post(
                    f"{self.settings.api_base_url}/internal/workers/heartbeat",
                    payload,
                    {"Authorization": f"Bearer {self.settings.worker_token}"},
                    self.settings.callback_timeout_seconds,
                )
            except Exception:
                continue

    def close(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)


@dataclass
class RunnerRuntime:
    settings: Settings
    redis: Any
    storage: ObjectStore
    sandbox: Sandbox
    transport: HttpTransport
    engine_factory: EngineFactory | None = None
    build_verifier: BuildVerifier | None = None
    publisher: ImagePublisher | None = None
    outbox: CallbackOutbox | None = None
    callback_sender: CallbackSender | None = None
    work_dir: Path | None = None

    def __post_init__(self) -> None:
        self.outbox = self.outbox or CallbackOutbox(self.settings.outbox_dir)
        self.callback_sender = self.callback_sender or CallbackSender(
            self.settings, self.outbox, self.transport
        )
        self.work_dir = self.work_dir or Path(os.environ.get("RUNNER_WORK_DIR", "./runner-work"))
        self.work_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_env(cls) -> "RunnerRuntime":
        settings = Settings.from_env()
        try:
            import boto3
            import redis
            from botocore.config import Config as BotoConfig
        except ImportError as exc:
            raise InfrastructureError("Install runner dependencies from pyproject.toml") from exc
        redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=False)
        s3 = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            config=BotoConfig(s3={"addressing_style": "path"}),
        )
        sandbox = DockerSandbox()
        return cls(
            settings=settings,
            redis=redis_client,
            storage=S3ObjectStore(s3, settings.s3_bucket),
            sandbox=sandbox,
            transport=UrllibTransport(),
            engine_factory=None,
            build_verifier=load_build_verifier(),
            publisher=DockerRegistryPublisher.from_env(sandbox.client),
        )

    def _url_for(self, payload: Mapping[str, Any], kind: str) -> str:
        resource_id = payload["submission_id"] if kind == "build" else payload["game_id"]
        suffix = "builds" if kind == "build" else "games"
        return f"{self.settings.api_base_url}/internal/{suffix}/{resource_id}"

    def _terminal_callback(self, item: PendingCallback, release_lease: bool = True) -> int:
        assert self.callback_sender and self.outbox
        status = self.callback_sender.send(item)
        if release_lease:
            RedisLease(self.redis, item.job_id, item.lease_token).release()
        return status

    def _resume_or_skip(self, job_id: str) -> bool:
        assert self.outbox
        pending = self.outbox.get(job_id)
        if pending:
            status = self._terminal_callback(pending)
            return status == 409 or pending.payload.get("status") in {
                "ready", "failed", "finished", "infra_error",
            }
        return self.outbox.is_completed(job_id)

    def _progress_callback(
        self, job: Mapping[str, Any], kind: str, token: str, body: dict[str, Any],
        guard: LeaseHeartbeat,
    ) -> bool:
        item = self._make_callback(job, kind, token, body)
        guard.check()
        status = self._terminal_callback(item, release_lease=False)
        if status == 409:
            RedisLease(self.redis, item.job_id, item.lease_token).release()
            return True
        return False

    def _make_callback(
        self, job: Mapping[str, Any], kind: str, token: str, body: dict[str, Any]
    ) -> PendingCallback:
        item = PendingCallback(job["job_id"], token, self._url_for(job, kind), body)
        assert self.callback_sender
        self.callback_sender.enqueue(item)
        return item

    @staticmethod
    def _bounded_message(exc: Exception) -> str:
        text = " ".join(str(exc).split()).strip()
        return (text or exc.__class__.__name__)[:MAX_CALLBACK_ERROR]

    def _build_result(
        self, job: Mapping[str, Any], status: str, image_tag: str | None,
        key: str | None, error: dict[str, str] | None,
    ) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "job_id": job["job_id"],
            "submission_id": job["submission_id"],
            "status": status,
            "image_tag": image_tag,
            "build_log_key": key,
            "error": error,
        }

    def build(self, payload: Any) -> dict[str, Any] | None:
        job = validate_build_job(payload)
        if self._resume_or_skip(job["job_id"]):
            return None
        lease = RedisLease(self.redis, job["job_id"])
        if not lease.claim():
            return None
        guard = LeaseHeartbeat(
            lease,
            on_lost=getattr(self.sandbox, "abort_current_build", None),
        )
        guard.start()
        image: str | None = None
        log_key: str | None = None
        log = bytearray(b"Build started\n")
        status, error = "ready", None
        if hasattr(self.sandbox, "last_build_log"):
            self.sandbox.last_build_log = b""
        try:
            stale = self._progress_callback(
                job, "build", lease.token, self._build_result(job, "building", None, None, None), guard,
            )
        except Exception:
            guard.close()
            raise
        if stale:
            guard.close()
            return None
        source_dir = self.work_dir / job["job_id"] / "source"
        try:
            if source_dir.parent.exists():
                shutil.rmtree(source_dir.parent)
            source_dir.mkdir(parents=True)
            source = self.storage.get(job["source_key"])
            if sha256(source) != job["source_sha256"]:
                raise InfrastructureError("Downloaded source ZIP does not match source_sha256")
            extract_source(source, source_dir, job["language"])
            guard.check()
            image = self.sandbox.build(job["language"], source_dir, job["submission_id"])
            log.extend(getattr(self.sandbox, "last_build_log", b""))
            if self.build_verifier is None:
                raise InfrastructureError(
                    "Build smoke-game verifier is missing; configure the engine/build verifier integration"
                )
            self.build_verifier.verify(image, job, timeout_seconds=150)
            guard.check()
            if self.publisher is not None:
                image = self.publisher.publish(image, job["submission_id"])
                guard.check()
        except BotBuildError as exc:
            status, error = "failed", {"code": "COMPILE_ERROR", "message": self._bounded_message(exc)}
            log.extend(getattr(self.sandbox, "last_build_log", b""))
        except UnsupportedLanguage as exc:
            status, image = "failed", None
            error = {"code": "INFRA_ERROR", "message": self._bounded_message(exc)}
        except LeaseLost:
            guard.close()
            raise
        except Exception as exc:
            status, image = "failed", None
            error = {"code": "INFRA_ERROR", "message": self._bounded_message(exc)}
            log.extend((self._bounded_message(exc) + "\n").encode("utf-8"))
            log.extend(getattr(self.sandbox, "last_build_log", b""))
        finally:
            shutil.rmtree(source_dir.parent, ignore_errors=True)
        try:
            guard.check()
        except LeaseLost:
            guard.close()
            raise
        try:
            if log:
                log_key = build_log_key(
                    self.storage,
                    staging_key("builds", job["submission_id"], job["job_id"], lease.token, "build.log"),
                    bytes(log[:MAX_BUILD_LOG_BYTES]),
                )
        except Exception as exc:
            status, image = "failed", None
            error = {"code": "INFRA_ERROR", "message": self._bounded_message(exc)}
        try:
            guard.check()
        except LeaseLost:
            guard.close()
            raise
        body = self._build_result(job, status, image, log_key, error)
        try:
            item = self._make_callback(job, "build", lease.token, body)
            guard.check()
            self._terminal_callback(item)
        finally:
            guard.close()
        return body

    @staticmethod
    def _result_value(result: Any, name: str, default: Any = None) -> Any:
        if isinstance(result, Mapping):
            return result.get(name, default)
        return getattr(result, name, default)

    @staticmethod
    def _callback_result(job: Mapping[str, Any], status: str, result: Any, replay_key: str | None,
                         log_key: str | None, duration_ms: int, error: dict[str, str] | None) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "job_id": job["job_id"],
            "game_id": job["game_id"],
            "attempt": job["attempt"],
            "status": status,
            "result": result,
            "replay_key": replay_key,
            "log_key": log_key,
            "duration_ms": duration_ms,
            "error": error,
        }

    @staticmethod
    def _validate_engine_result(job: Mapping[str, Any], game_result: Any) -> tuple[dict[str, Any], Mapping[str, Any], int]:
        winner = RunnerRuntime._result_value(game_result, "winner")
        reason = RunnerRuntime._result_value(game_result, "reason")
        plies = RunnerRuntime._result_value(game_result, "plies")
        duration = RunnerRuntime._result_value(game_result, "duration_ms")
        replay = RunnerRuntime._result_value(game_result, "replay")
        if winner not in {"BLUE", "RED"} or reason not in _GAME_REASONS:
            raise InfrastructureError("Engine returned an invalid winner or reason")
        if type(plies) is not int or plies < 0 or type(duration) is not int or duration < 0:
            raise InfrastructureError("Engine returned invalid plies or duration_ms")
        required = {
            "format", "engine_version", "ruleset_id", "map_id", "initial_fen",
            "players", "moves", "result",
        }
        if not isinstance(replay, Mapping) or set(replay) != required:
            raise InfrastructureError("Engine returned a replay with an invalid shape")
        config = job["config"]
        if (
            type(replay["format"]) is not int or replay["format"] != 1
            or replay["engine_version"] != config["engine_version"]
            or replay["ruleset_id"] != config["ruleset_id"]
            or replay["map_id"] != config["map_id"]
            or replay["initial_fen"] != config["initial_fen"]
        ):
            raise InfrastructureError("Engine replay metadata does not match the job config")
        replay_players = replay["players"]
        if not isinstance(replay_players, Mapping) or set(replay_players) != {"BLUE", "RED"}:
            raise InfrastructureError("Engine replay players have an invalid shape")
        for side in ("BLUE", "RED"):
            player = replay_players[side]
            expected = config["players"][side]
            if (
                not isinstance(player, Mapping)
                or set(player) != {"team", "submission_id", "bot_name"}
                or player.get("team") != expected["team"]
                or player.get("submission_id") != expected["submission_id"]
                or not isinstance(player.get("bot_name"), str)
                or not player["bot_name"]
            ):
                raise InfrastructureError(f"Engine replay {side} player does not match the job")
        moves = replay["moves"]
        if not isinstance(moves, list) or len(moves) != plies:
            raise InfrastructureError("Engine replay move count does not match result.plies")
        for index, move in enumerate(moves, start=1):
            if not isinstance(move, Mapping) or set(move) != {
                "ply", "side", "move", "think_ms", "clock_ms", "capture", "debug",
            }:
                raise InfrastructureError("Engine replay contains a malformed move")
            if (
                type(move["ply"]) is not int or move["ply"] != index
                or move["side"] not in {"BLUE", "RED"}
                or not isinstance(move["move"], str)
                or len(move["move"]) != 4
                or move["move"][0] not in "abcdefghi"
                or move["move"][1] not in "123456789"
                or move["move"][2] not in "abcdefghi"
                or move["move"][3] not in "123456789"
                or type(move["think_ms"]) is not int or move["think_ms"] < 0
                or type(move["clock_ms"]) is not int or move["clock_ms"] < 0
                or (move["capture"] is not None and not isinstance(move["capture"], str))
                or not isinstance(move["debug"], list)
                or any(not isinstance(line, str) for line in move["debug"])
            ):
                raise InfrastructureError("Engine replay contains an invalid move record")
        replay_result = replay["result"]
        expected_result = {"winner": winner, "reason": reason, "plies": plies}
        if not isinstance(replay_result, Mapping) or dict(replay_result) != expected_result:
            raise InfrastructureError("Engine replay result does not match GameResult")
        return expected_result, replay, duration

    def match(self, payload: Any) -> dict[str, Any] | None:
        job = validate_match_job(payload)
        if self._resume_or_skip(job["job_id"]):
            return None
        lease = RedisLease(self.redis, job["job_id"])
        if not lease.claim():
            return None
        bots: list[Any] = []

        def abort_bots() -> None:
            for bot in tuple(bots):
                abort = getattr(bot, "abort", None)
                if callable(abort):
                    abort()

        guard = LeaseHeartbeat(lease, on_lost=abort_bots)
        guard.start()
        try:
            stale = self._progress_callback(
                job, "match", lease.token,
                self._callback_result(job, "running", None, None, None, 0, None),
                guard,
            )
        except Exception:
            guard.close()
            raise
        if stale:
            guard.close()
            return None
        started = time.monotonic_ns()
        result_payload: dict[str, Any] | None = None
        status = "infra_error"
        result: dict[str, Any] | None = None
        replay_key: str | None = None
        log_key: str | None = None
        error: dict[str, str] | None = None
        replay_payload: Mapping[str, Any] | None = None
        logs = {"blue": b"", "red": b"", "blue_debug": b"", "red_debug": b""}
        game_duration_ms: int | None = None
        try:
            factory = self.engine_factory
            if factory is None:
                factory = load_engine_factory()
            engine = factory()
            blue = self.sandbox.start_bot(job["blue_image"], os.environ.get("RUNNER_CPUSET_BLUE", "0"))
            bots.append(blue)
            guard.check()
            red = self.sandbox.start_bot(job["red_image"], os.environ.get("RUNNER_CPUSET_RED", "1"))
            bots.append(red)
            guard.check()
            game_result = asyncio.run(engine.run_game(blue, red, job["config"]))
            guard.check()
            result, replay_payload, duration = self._validate_engine_result(job, game_result)
            game_duration_ms = duration
            status = "finished"
        except LeaseLost:
            guard.close()
            raise
        except Exception as exc:
            status = "infra_error"
            error = {"code": "INFRA_ERROR", "message": self._bounded_message(exc)}
        finally:
            for bot in bots:
                try:
                    awaitable = bot.close()
                    if hasattr(awaitable, "__await__"):
                        asyncio.run(awaitable)
                except Exception:
                    pass
            for side, bot in zip(("blue", "red"), bots):
                logs[side] = bytes(getattr(bot, "stderr", b""))[:1024 * 1024]
                logs[f"{side}_debug"] = bytes(getattr(bot, "debug", b""))[:1024 * 1024]
        try:
            guard.check()
        except LeaseLost:
            guard.close()
            raise
        duration_ms = game_duration_ms if game_duration_ms is not None else max(
            0, (time.monotonic_ns() - started) // 1_000_000
        )
        if status == "finished":
            # Re-upload now that stderr/debug have been completely drained; keys are unique to lease.
            try:
                assert replay_payload is not None
                replay_key, log_key = game_artifacts(
                    self.storage, job["game_id"], job["job_id"], lease.token,
                    dict(replay_payload), logs
                )
            except Exception as exc:
                status, result = "infra_error", None
                replay_key = log_key = None
                error = {"code": "INFRA_ERROR", "message": self._bounded_message(exc)}
        elif any(logs.values()):
            try:
                # Store diagnostics for failed infrastructure while preserving null game result.
                keys = []
                for name, content in logs.items():
                    key = staging_key("games", job["game_id"], job["job_id"], lease.token, f"{name}.log")
                    keys.append(self.storage.put_immutable(key, content[:1024 * 1024], "text/plain; charset=utf-8"))
                log_key = keys[0].rsplit("/", 1)[0] + "/"
            except Exception:
                log_key = None
        try:
            guard.check()
        except LeaseLost:
            guard.close()
            raise
        result_payload = self._callback_result(
            job, status, result, replay_key, log_key, duration_ms, error,
        )
        try:
            item = self._make_callback(job, "match", lease.token, result_payload)
            guard.check()
            self._terminal_callback(item)
        finally:
            guard.close()
        return result_payload
