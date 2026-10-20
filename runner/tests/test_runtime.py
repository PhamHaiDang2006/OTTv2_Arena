import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from ottv2_runner.config import Settings
from ottv2_runner.http import HttpResponse
from ottv2_runner.jobs import build_submission, configure_runtime
from ottv2_runner.lease import RedisLease
from ottv2_runner.runtime import RunnerRuntime


JOB_ID = "00000005-0000-4000-8000-000000000001"
SUBMISSION_ID = "00000003-0000-4000-8000-000000000001"
GAME_ID = "00000008-0000-4000-8000-000000000001"


def source_zip():
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("main.py", "print('READY')\n")
    return output.getvalue()


def build_payload(source):
    return {
        "schema_version": 1,
        "job_id": JOB_ID,
        "submission_id": SUBMISSION_ID,
        "language": "python",
        "source_key": f"submissions/{SUBMISSION_ID}/source.zip",
        "source_sha256": hashlib.sha256(source).hexdigest(),
        "engine_version": "1.0.0",
    }


def match_payload():
    blue = {"team": "blue-team", "submission_id": SUBMISSION_ID}
    red = {"team": "red-team", "submission_id": "00000004-0000-4000-8000-000000000001"}
    players = {"BLUE": blue, "RED": red}
    return {
        "schema_version": 1,
        "job_id": "00000007-0000-4000-8000-000000000001",
        "game_id": GAME_ID,
        "attempt": 1,
        "blue_image": "sha256:" + "a" * 64,
        "red_image": "sha256:" + "b" * 64,
        "map_id": "standard",
        "engine_version": "1.0.0",
        "players": players,
        "config": {
            "engine_version": "1.0.0",
            "ruleset_id": "dev-v1",
            "map_id": "standard",
            "initial_fen": "9/pbkpbkpbk/kpbkpbkpb/9/9/9/BPKBPKBPK/KBPKBPKBP/9",
            "players": json.loads(json.dumps(players)),
            "budget_ms": 60000,
            "init_ms": 10000,
            "grace_ms": 50,
            "hard_timeout_extra_ms": 1000,
            "max_turns": 300,
            "seed": 42,
        },
    }


class FakeRedis:
    def __init__(self):
        self.data = {}

    def set(self, key, value, nx=False, px=None):
        if nx and key in self.data:
            return False
        self.data[key] = value
        return True

    def get(self, key):
        return self.data.get(key)

    def eval(self, script, key_count, key, token, *_):
        if self.data.get(key) != token:
            return 0
        if "PEXPIRE" in script:
            return 1
        if "DEL" in script:
            del self.data[key]
            return 1
        return 0


class FakeStorage:
    def __init__(self, source=b""):
        self.source = source
        self.objects = {}

    def get(self, key):
        return self.source

    def put_immutable(self, key, data, content_type, content_encoding=None):
        if key in self.objects:
            raise RuntimeError("immutable object already exists")
        self.objects[key] = (data, content_type, content_encoding)
        return key


class FakeTransport:
    def __init__(self, statuses=()):
        self.statuses = list(statuses)
        self.requests = []

    def post(self, url, payload, headers, timeout):
        self.requests.append((url, payload, headers, timeout))
        return HttpResponse(self.statuses.pop(0) if self.statuses else 200)


class FakeSandbox:
    def __init__(self):
        self.build_count = 0
        self.started = 0
        self.last_build_log = b"compiler output"

    def build(self, language, source_dir, submission_id):
        self.build_count += 1
        return "sha256:" + "c" * 64

    def start_bot(self, image, cpu):
        self.started += 1
        return FakeBot()


class FakeBot:
    started_at_ns = 1
    stderr = b"bot stderr"
    debug = b"# debug"

    async def close(self):
        return None


class FakeVerifier:
    def verify(self, image, job, timeout_seconds):
        self.args = (image, job, timeout_seconds)


class FakeEngine:
    async def run_game(self, blue, red, config):
        players = {
            "BLUE": {**config["players"]["BLUE"], "bot_name": "FakeBlue"},
            "RED": {**config["players"]["RED"], "bot_name": "FakeRed"},
        }
        return {
            "winner": "BLUE",
            "reason": "GOAL",
            "plies": 0,
            "duration_ms": 1,
            "replay": {
                "format": 1,
                "engine_version": config["engine_version"],
                "ruleset_id": config["ruleset_id"],
                "map_id": config["map_id"],
                "initial_fen": config["initial_fen"],
                "players": players,
                "moves": [],
                "result": {"winner": "BLUE", "reason": "GOAL", "plies": 0},
            },
        }


class RunnerRuntimeTests(unittest.TestCase):
    def test_settings_use_vps2_compose_environment_names(self):
        environment = {
            "INTERNAL_API_BASE_URL": "http://10.77.0.1:8000/api/v1",
            "WORKER_API_TOKEN": "worker-token",
            "REDIS_URL": "redis://:password@10.77.0.1:6379/0",
            "S3_ENDPOINT_URL": "http://10.77.0.1:9000",
            "S3_ACCESS_KEY_ID": "worker-key",
            "S3_SECRET_ACCESS_KEY": "worker-secret",
            "S3_BUCKET": "ottv2",
            "RUNNER_OUTBOX_DIR": "/var/lib/ottv2/outbox",
            "RUNNER_WORKER_ID": "build-worker",
        }
        with patch.dict("os.environ", environment, clear=True):
            settings = Settings.from_env()
        self.assertEqual(settings.worker_token, "worker-token")
        self.assertEqual(settings.s3_endpoint_url, "http://10.77.0.1:9000")
        self.assertEqual(settings.s3_access_key, "worker-key")
        self.assertEqual(settings.s3_bucket, "ottv2")
        self.assertEqual(settings.outbox_dir, Path("/var/lib/ottv2/outbox"))
        self.assertEqual(settings.worker_id, "build-worker")

    def create_runtime(self, tmp_path, storage=None, transport=None, engine_factory=None, verifier=None, sandbox=None):
        settings = Settings(
            api_base_url="http://backend",
            worker_token="worker-test-token",
            redis_url="redis://unused",
            s3_endpoint_url="http://minio",
            s3_access_key="key",
            s3_secret_key="secret",
            s3_bucket="arena",
            outbox_dir=Path(tmp_path) / "outbox",
            worker_id="test-worker",
        )
        return RunnerRuntime(
            settings=settings,
            redis=FakeRedis(),
            storage=storage or FakeStorage(),
            sandbox=sandbox or FakeSandbox(),
            transport=transport or FakeTransport(),
            engine_factory=engine_factory,
            build_verifier=verifier,
            work_dir=Path(tmp_path) / "work",
        )

    def test_callback_transport_failure_retries_saved_callback_without_rebuilding(self):
        with tempfile.TemporaryDirectory() as directory:
            source = source_zip()
            transport = FakeTransport([503, 200, 200])
            runtime = self.create_runtime(
                directory,
                storage=FakeStorage(source),
                transport=transport,
                verifier=FakeVerifier(),
            )
            runtime.callback_sender.sleep = lambda _: None
            configure_runtime(runtime)
            try:
                result = build_submission(build_payload(source))
            finally:
                configure_runtime(None)
            self.assertEqual(result["status"], "ready")
            self.assertIsNotNone(result["build_log_key"])
            self.assertEqual(runtime.sandbox.build_count, 1)
            self.assertEqual([request[1]["status"] for request in transport.requests], ["building", "building", "ready"])

            # RQ duplicate after terminal receipt is acknowledged from the local journal.
            restarted_runtime = self.create_runtime(directory, storage=FakeStorage(source))
            self.assertIsNone(restarted_runtime.build(build_payload(source)))
            self.assertEqual(runtime.sandbox.build_count, 1)
            completed = Path(directory) / "outbox" / "completed" / f"{JOB_ID}.terminal.json"
            self.assertNotIn("lease_token", completed.read_text(encoding="utf-8"))

    def test_missing_engine_is_explicit_infrastructure_error_not_a_bot_loss(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = self.create_runtime(directory)
            callback = runtime.match(match_payload())
            self.assertEqual(callback["status"], "infra_error")
            self.assertEqual(callback["error"]["code"], "INFRA_ERROR")
            self.assertIsNone(callback["result"])
            self.assertEqual(runtime.sandbox.started, 0)

    def test_injected_engine_runs_and_stores_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            transport = FakeTransport()
            storage = FakeStorage()
            sandbox = FakeSandbox()
            runtime = self.create_runtime(
                directory, storage=storage, transport=transport,
                engine_factory=lambda: FakeEngine(), sandbox=sandbox,
            )
            callback = runtime.match(match_payload())
            self.assertEqual(callback["status"], "finished")
            self.assertEqual(callback["result"], {"winner": "BLUE", "reason": "GOAL", "plies": 0})
            self.assertEqual(sandbox.started, 2)
            token = transport.requests[-1][2]["X-Worker-Lease"]
            self.assertTrue(callback["replay_key"].startswith(f"staging/{match_payload()['job_id']}/{token}/games/{GAME_ID}/"))
            replay_object = storage.objects[callback["replay_key"]]
            self.assertEqual(replay_object[1], "application/json")
            self.assertEqual(replay_object[2], "gzip")
            self.assertEqual(transport.requests[-1][1]["status"], "finished")

    def test_redis_lease_renew_and_release_are_owner_token_fenced(self):
        client = FakeRedis()
        owner = RedisLease(client, JOB_ID, token="owner-token")
        other = RedisLease(client, JOB_ID, token="other-token")
        self.assertTrue(owner.claim())
        self.assertFalse(other.claim())
        self.assertTrue(owner.renew())
        self.assertFalse(other.release())
        self.assertTrue(owner.release())


if __name__ == "__main__":
    unittest.main()
