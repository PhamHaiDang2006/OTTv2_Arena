"""Live dev acceptance run: real Redis, MinIO, Docker and registry with a fake backend.

Prereqs: `docker compose -f infra/docker-compose.dev.yml up -d` (infra/.env present), the
dev registry on 127.0.0.1:5000, and `pip install -e runner`. Uses the dev-only stand-in
engine in ottv2_runner.devkit, so results prove plumbing, not game rules.

    python scripts/dev_e2e.py
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import sys
import tempfile
import threading
import uuid
import zipfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYTHON_IMAGE = os.environ.get(
    "RUNNER_IMAGE_PYTHON",
    "python@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258",
)
FEN = "9/pbkpbkpbk/kpbkpbkpb/9/9/9/BPKBPKBPK/KBPKBPKBP/9"

BOTS = {
    "good": (
        "import sys\n"
        "print('READY samplebot', flush=True)\n"
        "for line in sys.stdin:\n"
        "    line = line.strip()\n"
        "    if line.startswith('INIT'):\n"
        "        print('OK', flush=True)\n"
        "    elif line == 'GO':\n"
        "        print('# thinking', flush=True)\n"
        "        print('MOVE c3d4', flush=True)\n"
        "    elif line.startswith('END'):\n"
        "        break\n"
    ),
    "midcrash": (
        "import sys\n"
        "print('READY crashy', flush=True)\n"
        "for line in sys.stdin:\n"
        "    if line.startswith('INIT'):\n"
        "        print('OK', flush=True)\n"
        "    elif line.strip() == 'GO':\n"
        "        print('# about to crash', flush=True)\n"
        "        sys.exit(4)\n"
    ),
    "hang": (
        "import sys, time\n"
        "print('READY hangy', flush=True)\n"
        "for line in sys.stdin:\n"
        "    if line.startswith('INIT'):\n"
        "        print('OK', flush=True)\n"
        "    elif line.strip() == 'GO':\n"
        "        time.sleep(3600)\n"
    ),
    "slow": (
        "import sys, time\n"
        "print('READY slowy', flush=True)\n"
        "for line in sys.stdin:\n"
        "    if line.startswith('INIT'):\n"
        "        print('OK', flush=True)\n"
        "    elif line.strip() == 'GO':\n"
        "        time.sleep(8)\n"
        "        print('MOVE c3d4', flush=True)\n"
        "    elif line.startswith('END'):\n"
        "        break\n"
    ),
    "crash": "import sys\nsys.exit(3)\n",
    "cpp": (
        "#include <iostream>\n#include <string>\n"
        "int main() {\n"
        "  std::cout << \"READY cppbot\" << std::endl;\n"
        "  std::string line;\n"
        "  while (std::getline(std::cin, line)) {\n"
        "    if (line.rfind(\"INIT\", 0) == 0) std::cout << \"OK\" << std::endl;\n"
        "    else if (line == \"GO\") { std::cout << \"# cpp thinking\" << std::endl; std::cout << \"MOVE c3d4\" << std::endl; }\n"
        "    else if (line.rfind(\"END\", 0) == 0) break;\n"
        "  }\n"
        "}\n"
    ),
    "cpp_broken": "int main( { return 0; }\n",
    "syntax": "def broken(:\n",
}


def load_env(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values


class Recorder(BaseHTTPRequestHandler):
    calls: list[tuple[str, dict, dict]] = []
    fail_terminal = False
    rejected = 0

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        if Recorder.fail_terminal and body.get("status") in {"ready", "failed", "finished", "infra_error"}:
            Recorder.rejected += 1
            self.send_response(503)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        Recorder.calls.append((self.path, dict(self.headers), body))
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *_):
        pass


def zip_source(code: str, filename: str = "main.py") -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr(filename, code)
    return out.getvalue()


def main() -> int:
    env = load_env(ROOT / "infra" / ".env")
    redis_url = env["REDIS_URL"].replace("@redis:", "@localhost:")
    server = HTTPServer(("127.0.0.1", 0), Recorder)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    workdir = tempfile.mkdtemp(prefix="ottv2-e2e-")
    os.environ.update({
        "INTERNAL_API_BASE_URL": f"http://127.0.0.1:{server.server_port}/api/v1",
        "WORKER_API_TOKEN": "dev-token",
        "REDIS_URL": redis_url,
        "S3_ENDPOINT_URL": f"http://localhost:{env.get('MINIO_PORT', '9000')}",
        "S3_ACCESS_KEY_ID": env["MINIO_ROOT_USER"],
        "S3_SECRET_ACCESS_KEY": env["MINIO_ROOT_PASSWORD"],
        "S3_BUCKET": "ottv2-e2e",
        "RUNNER_OUTBOX_DIR": os.path.join(workdir, "outbox"),
        "RUNNER_WORK_DIR": os.path.join(workdir, "work"),
        "RUNNER_WORKER_ID": "dev-e2e",
        "RUNNER_IMAGE_PYTHON": PYTHON_IMAGE,
        "RUNNER_IMAGE_CPP": PYTHON_IMAGE,
        "RUNNER_BUILD_IMAGE_CPP": os.environ.get(
            "RUNNER_BUILD_IMAGE_CPP",
            "gcc@sha256:1d71f0f3450214bef38fe09e6f610fb6cca90cf97b43f4ce845bfc32a4168818",
        ),
        "REGISTRY_URL": "127.0.0.1:5000",
        "OTTv2_ENGINE_FACTORY": "ottv2_runner.devkit:make_engine",
        "OTTv2_BUILD_VERIFIER": "ottv2_runner.devkit:make_build_verifier",
    })
    import boto3
    import docker
    import redis
    from botocore.config import Config
    from rq import Queue, SimpleWorker

    s3 = boto3.client(
        "s3", endpoint_url=os.environ["S3_ENDPOINT_URL"],
        aws_access_key_id=os.environ["S3_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["S3_SECRET_ACCESS_KEY"],
        config=Config(s3={"addressing_style": "path"}),
    )
    try:
        s3.create_bucket(Bucket="ottv2-e2e")
    except s3.exceptions.BucketAlreadyOwnedByYou:
        pass
    connection = redis.Redis.from_url(redis_url)
    docker_client = docker.from_env()
    containers_before = {c.id for c in docker_client.containers.list(all=True)}
    failures: list[str] = []

    def check(condition: bool, message: str) -> None:
        print(("PASS " if condition else "FAIL ") + message, flush=True)
        if not condition:
            failures.append(message)

    def drain(queue_name: str) -> None:
        queue = Queue(queue_name, connection=connection)
        SimpleWorker([queue], connection=connection).work(burst=True)

    def enqueue_build(payload: dict) -> None:
        Queue("build", connection=connection).enqueue(
            "ottv2_runner.jobs.build_submission", payload, job_timeout=300
        )
        drain("build")

    def run_build(kind: str) -> dict:
        submission_id, job_id = str(uuid.uuid4()), str(uuid.uuid4())
        language = "cpp" if kind.startswith("cpp") else "python"
        data = zip_source(BOTS[kind], "main.cpp" if language == "cpp" else "main.py")
        key = f"submissions/{submission_id}/source.zip"
        s3.put_object(Bucket="ottv2-e2e", Key=key, Body=data)
        payload = {
            "schema_version": 1, "job_id": job_id, "submission_id": submission_id,
            "language": language, "source_key": key,
            "source_sha256": hashlib.sha256(data).hexdigest(), "engine_version": "1.0.0",
        }
        enqueue_build(payload)
        calls = [c for c in Recorder.calls if c[0].endswith(f"/internal/builds/{submission_id}")]
        return {"payload": payload, "calls": calls}

    good = run_build("good")
    final = good["calls"][-1][2] if good["calls"] else {}
    check(final.get("status") == "ready", f"good bot build is ready ({final.get('status')} {final.get('error')})")
    image_tag = final.get("image_tag") or ""
    check(image_tag.startswith("127.0.0.1:5000/ottv2-bot@sha256:"), f"image_tag is registry digest ({image_tag})")
    try:
        s3.head_object(Bucket="ottv2-e2e", Key=final["build_log_key"])
        check(True, "build log stored in MinIO")
    except Exception:
        check(False, "build log stored in MinIO")
    check(bool(good["calls"]) and all(c[1].get("X-Worker-Lease") for c in good["calls"]),
          "callbacks carry X-Worker-Lease")

    before = len(Recorder.calls)
    enqueue_build(good["payload"])
    check(len(Recorder.calls) == before, "duplicate build job sends no new callbacks")

    for kind in ("crash", "syntax"):
        result = run_build(kind)
        status = result["calls"][-1][2].get("status") if result["calls"] else None
        check(status == "failed", f"{kind} bot build is failed ({status})")

    if image_tag:
        blue = {"team": "blue-team", "submission_id": good["payload"]["submission_id"]}
        red = {"team": "red-team", "submission_id": good["payload"]["submission_id"]}
        players = {"BLUE": blue, "RED": red}
        game_id, job_id = str(uuid.uuid4()), str(uuid.uuid4())
        match = {
            "schema_version": 1, "job_id": job_id, "game_id": game_id, "attempt": 1,
            "blue_image": image_tag, "red_image": image_tag, "map_id": "standard",
            "engine_version": "1.0.0", "players": players,
            "config": {
                "engine_version": "1.0.0", "ruleset_id": "dev-v1", "map_id": "standard",
                "initial_fen": FEN, "players": json.loads(json.dumps(players)),
                "budget_ms": 60000, "init_ms": 10000, "grace_ms": 50,
                "hard_timeout_extra_ms": 1000, "max_turns": 300, "seed": 42,
            },
        }
        Queue("match:scrimmage", connection=connection).enqueue(
            "ottv2_runner.jobs.run_match", match, job_timeout=300
        )
        drain("match:scrimmage")
        calls = [c for c in Recorder.calls if c[0].endswith(f"/internal/games/{game_id}")]
        final = calls[-1][2] if calls else {}
        check(final.get("status") == "finished", f"match finished ({final.get('status')} {final.get('error')})")
        try:
            s3.head_object(Bucket="ottv2-e2e", Key=final["replay_key"])
            check(True, "replay_key object exists in MinIO")
        except Exception:
            check(False, "replay_key object exists in MinIO")
        listing = s3.list_objects_v2(Bucket="ottv2-e2e", Prefix=final.get("log_key") or "no-such-prefix")
        logs = [item["Key"] for item in listing.get("Contents", []) if item["Key"].endswith(".log")]
        check(len(logs) == 4, f"log_key prefix holds 4 staged log objects ({len(logs)})")

    leftover_check_placeholder = None
    from ottv2_runner import jobs

    runtime = jobs._get_runtime()
    runtime.callback_sender.sleep = lambda _: None

    class WorkerDied(Exception):
        pass

    sleeps = {"count": 0}

    def die_after_retries(_: float) -> None:
        sleeps["count"] += 1
        if sleeps["count"] > 2:
            raise WorkerDied

    Recorder.fail_terminal = True
    runtime.callback_sender.sleep = die_after_retries
    outage = run_build("good")
    runtime.callback_sender.sleep = lambda _: None
    check(Recorder.rejected >= 1 and not any(c[2].get("status") == "ready" for c in outage["calls"]),
          "backend outage: terminal callback was not accepted")
    pending = runtime.outbox.pending()
    check(len(pending) == 1, f"backend outage: result kept in durable outbox ({len(pending)})")
    saved_tag = pending[0].payload.get("image_tag") if pending else None
    Recorder.fail_terminal = False
    for item in runtime.outbox.pending():
        runtime._terminal_callback(item)
    delivered = [c for c in Recorder.calls
                 if c[0].endswith(f"/internal/builds/{outage['payload']['submission_id']}")]
    check(bool(delivered) and delivered[-1][2].get("status") == "ready"
          and delivered[-1][2].get("image_tag") == saved_tag,
          "backend recovery: flush-outbox delivers the saved result without rebuilding")
    check(not runtime.outbox.pending(), "backend recovery: outbox drained")

    # C++: compile in the isolated builder, then run the binary in a runtime image.
    cpp = run_build("cpp")
    cpp_final = cpp["calls"][-1][2] if cpp["calls"] else {}
    check(cpp_final.get("status") == "ready", f"cpp bot build is ready ({cpp_final.get('status')} {cpp_final.get('error')})")
    cpp_tag = cpp_final.get("image_tag") or ""
    if cpp_tag:
        # Pair the C++ image against the python image in a real match.
        sides = {"BLUE": {"team": "b", "submission_id": cpp["payload"]["submission_id"]},
                 "RED": {"team": "r", "submission_id": good["payload"]["submission_id"]}}
        cpp_game, cpp_job = str(uuid.uuid4()), str(uuid.uuid4())
        Queue("match:scrimmage", connection=connection).enqueue("ottv2_runner.jobs.run_match", {
            "schema_version": 1, "job_id": cpp_job, "game_id": cpp_game, "attempt": 1,
            "blue_image": cpp_tag, "red_image": image_tag, "map_id": "standard",
            "engine_version": "1.0.0", "players": sides,
            "config": {
                "engine_version": "1.0.0", "ruleset_id": "dev-v1", "map_id": "standard",
                "initial_fen": FEN, "players": json.loads(json.dumps(sides)),
                "budget_ms": 60000, "init_ms": 10000, "grace_ms": 50,
                "hard_timeout_extra_ms": 1000, "max_turns": 300, "seed": 11,
            },
        }, job_timeout=300)
        drain("match:scrimmage")
        cpp_calls = [c[2] for c in Recorder.calls if c[0].endswith(f"/internal/games/{cpp_game}")]
        check(bool(cpp_calls) and cpp_calls[-1].get("status") == "finished",
              f"cpp vs python match finished ({cpp_calls[-1].get('status') if cpp_calls else None})")
    broken = run_build("cpp_broken")
    broken_status = broken["calls"][-1][2].get("status") if broken["calls"] else None
    check(broken_status == "failed", f"cpp compile error build is failed ({broken_status})")

    # Failure scenarios during a match. The build verifier is bypassed so misbehaving
    # images can be built; the real engine decides forfeits, the dev engine just errors.
    real_verifier = runtime.build_verifier
    runtime.build_verifier = type("NoVerify", (), {"verify": lambda self, *a, **k: None})()
    images = {}
    for kind in ("midcrash", "hang", "slow"):
        built = run_build(kind)
        images[kind] = (built["calls"][-1][2] if built["calls"] else {}).get("image_tag")
    runtime.build_verifier = real_verifier
    check(all(images.values()), f"misbehaving bots built for match tests ({images})")

    def run_match(blue_image: str, red_image: str, budget_ms: int = 60000, during=None) -> tuple[str, list]:
        game_id, match_job = str(uuid.uuid4()), str(uuid.uuid4())
        sides = {"BLUE": {"team": "b", "submission_id": game_id}, "RED": {"team": "r", "submission_id": game_id}}
        payload = {
            "schema_version": 1, "job_id": match_job, "game_id": game_id, "attempt": 1,
            "blue_image": blue_image, "red_image": red_image, "map_id": "standard",
            "engine_version": "1.0.0", "players": sides,
            "config": {
                "engine_version": "1.0.0", "ruleset_id": "dev-v1", "map_id": "standard",
                "initial_fen": FEN, "players": json.loads(json.dumps(sides)),
                "budget_ms": budget_ms, "init_ms": 10000, "grace_ms": 50,
                "hard_timeout_extra_ms": 1000, "max_turns": 300, "seed": 7,
            },
        }
        Queue("match:scrimmage", connection=connection).enqueue(
            "ottv2_runner.jobs.run_match", payload, job_timeout=300
        )
        if during:
            threading.Thread(target=during, args=(match_job,), daemon=True).start()
        drain("match:scrimmage")
        return match_job, [c[2] for c in Recorder.calls if c[0].endswith(f"/internal/games/{game_id}")]

    if all(images.values()):
        for kind, extra in (("midcrash", {}), ("hang", {})):
            _, calls = run_match(image_tag, images[kind], **extra)
            terminal = calls[-1] if calls else {}
            check(terminal.get("status") == "infra_error" and terminal.get("result") is None,
                  f"{kind} bot mid-match is reported as infra_error without a result ({terminal.get('status')})")
            check(bool(terminal.get("log_key")), f"{kind} bot mid-match still stores diagnostic logs")

        def steal_lease(job_id: str) -> None:
            import time
            time.sleep(3)
            connection.set(f"ottv2:lease:{job_id}", "someone-else", px=60000)

        job_id, calls = run_match(image_tag, images["slow"], during=steal_lease)
        check(not any(c.get("status") in {"finished", "infra_error"} for c in calls),
              "lease lost mid-match: no terminal callback is sent")
        connection.delete(f"ottv2:lease:{job_id}")

        # A job whose previous worker died still holds a short-lived lease.
        game_id, dead_job = str(uuid.uuid4()), str(uuid.uuid4())
        sides = {"BLUE": {"team": "b", "submission_id": game_id}, "RED": {"team": "r", "submission_id": game_id}}
        redelivered = {
            "schema_version": 1, "job_id": dead_job, "game_id": game_id, "attempt": 1,
            "blue_image": image_tag, "red_image": image_tag, "map_id": "standard",
            "engine_version": "1.0.0", "players": sides,
            "config": {
                "engine_version": "1.0.0", "ruleset_id": "dev-v1", "map_id": "standard",
                "initial_fen": FEN, "players": json.loads(json.dumps(sides)),
                "budget_ms": 60000, "init_ms": 10000, "grace_ms": 50,
                "hard_timeout_extra_ms": 1000, "max_turns": 300, "seed": 7,
            },
        }
        import time
        connection.set(f"ottv2:lease:{dead_job}", "dead-worker", px=4000)
        Queue("match:scrimmage", connection=connection).enqueue(
            "ottv2_runner.jobs.run_match", redelivered, job_timeout=300)
        drain("match:scrimmage")
        early = [c for c in Recorder.calls if c[0].endswith(f"/internal/games/{game_id}")]
        check(not early, "redelivery while a dead worker's lease is live is skipped")
        time.sleep(4.2)
        Queue("match:scrimmage", connection=connection).enqueue(
            "ottv2_runner.jobs.run_match", redelivered, job_timeout=300)
        drain("match:scrimmage")
        late = [c[2] for c in Recorder.calls if c[0].endswith(f"/internal/games/{game_id}")]
        check(bool(late) and late[-1].get("status") == "finished",
              "redelivery after the dead worker's lease expires completes the match")

    leftover = [c for c in docker_client.containers.list(all=True) if c.id not in containers_before]
    check(not leftover, f"no leftover containers ({[c.name for c in leftover]})")
    print(f"\n{len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
