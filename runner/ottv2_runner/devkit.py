"""Development-only stand-ins for the OTTv2 engine adapter and build smoke verifier.

These speak the bot line protocol (architecture.md section 4) so the runner's Docker,
storage, lease and callback plumbing can be exercised end to end. They implement NO game
rules and must never be used for an official tournament; replace them with the real engine
adapter through OTTv2_ENGINE_FACTORY / OTTv2_BUILD_VERIFIER.
"""
from __future__ import annotations

import asyncio
import re
import time
from collections.abc import Mapping
from typing import Any

from .errors import BotBuildError, InfrastructureError

_MOVE = re.compile(r"MOVE ([a-i][1-9][a-i][1-9])")
_MOVES_PER_SIDE = 2


async def _handshake(bot: Any, side: str, config: Mapping[str, Any]) -> str:
    await bot.send_line("OTTV2 1")
    ready = await bot.read_line(config["init_ms"])
    if not ready.startswith("READY"):
        raise BotBuildError("Bot did not answer the protocol greeting with READY")
    name = ready[len("READY"):].strip() or f"{side.lower()}-bot"
    await bot.send_line(
        f"INIT side={side} budget_ms={config['budget_ms']} init_ms={config['init_ms']} "
        f"max_turns={config['max_turns']}"
    )
    if await bot.read_line(config["init_ms"]) != "OK":
        raise BotBuildError("Bot did not answer INIT with OK")
    return name


async def _read_move(bot: Any, config: Mapping[str, Any], fen: str, ply: int, side: str) -> tuple[str, int, list[str]]:
    budget = config["budget_ms"]
    await bot.send_line(f"STATE {fen} {side} {ply - 1} {budget} {budget}")
    await bot.send_line("GO")
    started = time.monotonic_ns()
    debug: list[str] = []
    while True:
        line = await bot.read_line(budget + config["grace_ms"])
        if line.startswith("#"):
            debug.append(line)
            continue
        match = _MOVE.fullmatch(line)
        if match is None:
            raise BotBuildError("Bot sent a malformed MOVE line")
        return match.group(1), (time.monotonic_ns() - started) // 1_000_000, debug


class DevSmokeEngine:
    async def run_game(self, blue_io: Any, red_io: Any, config: Mapping[str, Any]) -> dict[str, Any]:
        started = time.monotonic_ns()
        names = {
            "BLUE": await _handshake(blue_io, "BLUE", config),
            "RED": await _handshake(red_io, "RED", config),
        }
        bots = {"BLUE": blue_io, "RED": red_io}
        moves: list[dict[str, Any]] = []
        for _ in range(_MOVES_PER_SIDE):
            for side in ("BLUE", "RED"):
                move, think_ms, debug = await _read_move(
                    bots[side], config, config["initial_fen"], len(moves) + 1, side
                )
                moves.append({
                    "ply": len(moves) + 1, "side": side, "move": move, "think_ms": think_ms,
                    "clock_ms": max(config["budget_ms"] - think_ms, 0), "capture": None, "debug": debug,
                })
        for bot, outcome in ((blue_io, "WIN"), (red_io, "LOSS")):
            await bot.send_line(f"END {outcome} MOVE_LIMIT")
        result = {"winner": "BLUE", "reason": "MOVE_LIMIT", "plies": len(moves)}
        return {
            **result,
            "duration_ms": (time.monotonic_ns() - started) // 1_000_000,
            "replay": {
                "format": 1,
                "engine_version": config["engine_version"],
                "ruleset_id": config["ruleset_id"],
                "map_id": config["map_id"],
                "initial_fen": config["initial_fen"],
                "players": {
                    side: {**config["players"][side], "bot_name": names[side]} for side in ("BLUE", "RED")
                },
                "moves": moves,
                "result": result,
            },
        }


def make_engine() -> DevSmokeEngine:
    return DevSmokeEngine()


class DevBuildVerifier:
    """Starts the built image, performs the READY/INIT handshake and one MOVE."""

    def __init__(self, sandbox: Any | None = None):
        if sandbox is None:
            from .sandbox import DockerSandbox

            sandbox = DockerSandbox()
        self.sandbox = sandbox

    def verify(self, image: str, job: Mapping[str, Any], timeout_seconds: int = 150) -> None:
        config = {"budget_ms": 5000, "init_ms": 10000, "grace_ms": 50, "max_turns": 300}
        fen = "9/pbkpbkpbk/kpbkpbkpb/9/9/9/BPKBPKBPK/KBPKBPKBP/9"
        bot = self.sandbox.start_bot(image, "0")

        async def run() -> None:
            try:
                await asyncio.wait_for(_handshake(bot, "BLUE", config), timeout_seconds)
                await asyncio.wait_for(_read_move(bot, config, fen, 1, "BLUE"), timeout_seconds)
            finally:
                await bot.close()

        try:
            asyncio.run(run())
        except (BotBuildError, InfrastructureError):
            raise
        except (TimeoutError, EOFError) as exc:
            raise BotBuildError("Bot did not complete the smoke handshake in time") from exc


def make_build_verifier() -> DevBuildVerifier:
    return DevBuildVerifier()
