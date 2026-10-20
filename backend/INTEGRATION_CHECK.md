# Backend / runner / engine integration — 2026-10-19

Contract v1.0.0, engine 1.0.0, runner 0.1.0, development ruleset dev-v1.
Changes are local on `engine-starter`; no commit, push, merge or publication.

## Changes and affected consumers

- Runner artifacts now use ownership prefix `staging/{job_id}/{lease_token}/`,
  matching backend validation. Resource kind/id remain nested under that prefix.
- Successful games and infrastructure failures share `blue.stderr.log` and
  `red.stderr.log`; backend can retain and expose both through authorized APIs.
- Backend rejects submissions built for another engine version before creating
  game jobs or freezing a tournament snapshot. No database migration is needed.
- Shared callback fixtures were corrected in `contracts/build.mjs` and regenerated
  with `node contracts/build.mjs`. HTTP DTOs and engine public API are unchanged.
- Added backend Dockerfile, VPS1 scheduler service, real-engine adapter values
  in VPS2 env example, disposable test Compose and integration CI.
- Updated backend/runner/infra instructions and resolved staging/version questions
  in DECISIONS.md. Contract validator dependencies stay in `contracts/.deps` to
  avoid replacing the newer JSON Schema dependencies pinned by backend/uv.lock.

Backend, runner and engine must be present together for the integration suite.
Build worker image from `runner/Dockerfile.engine`, Python bot base from
`engine/Dockerfile.bot`, backend from `backend/Dockerfile`, all at repo root.
Run `python -m app.cli migrate` once before starting API and scheduler.

## Checks completed

Tools: Python 3.12.14 on Windows, uv 0.13.1, g++ from MSYS2, Docker Desktop Linux
engine. Backend dependencies installed from its frozen lockfile.

| Check | Result |
| --- | --- |
| Backend `.venv/Scripts/python.exe -m pytest -q --tb=short` | 193 passed; 7 HTTP test-client deprecation warnings; 684.88 seconds |
| Final integration + HTTP surface rerun after restoring locked dependencies | 12 passed; contract validator passed again |
| `python -m unittest discover -s engine/tests -v` | 18 passed |
| `python -m unittest discover -s runner/tests -v` | 23 passed |
| `python starter-kits/tests/check_kits.py` | 1,000 positions, both sides, Python/C++ agree |
| `python starter-kits/tests/play_kits.py` | All 8 Python/C++ random/greedy matches passed; 4 source ZIPs packaged |
| `python engine/scripts/generate_fixtures.py` + `git diff --exit-code -- engine/fixtures` | 6 replays and 1,000 positions regenerated with no drift |
| `python engine/scripts/stress.py --games 10000 --output engine/dist/integration-stress-report.json` | 10,000 deterministic games passed; BLUE 48.75%; hash matches earlier fixture report |
| `node contracts/build.mjs --check` | No generated drift |
| `python contracts/validate.py` | 85 definitions, 65 operations, 133 fixture cases passed |
| `python contracts/test_mock.py` | 5 passed |
| `npm run typecheck --prefix contracts` | Passed |
| `ruff check backend/app backend/tests backend/migrations backend/scripts` | Passed |
| `git diff --check` | Passed |
| Compose config with dev/VPS1/VPS2 example env files | All passed |
| Docker builds: backend, engine-enabled worker, Python bot base | All passed |
| Backend image: migration into a separate empty DB, scheduler start/stop, HTTP capabilities/docs | Passed |
| Worker image: configured engine adapter import and CLI entrypoint | Passed |
| Real Docker Python kit smoke | Build, engine verifier and a 240-ply game passed; bot containers removed |

The real Docker smoke used the trusted Python kit, a locally built bot base and
the actual `DockerSandbox` / `EngineBuildVerifier` / engine adapter. It does not
certify malicious-bot isolation or registry publication. Temporary script:
`.venv/docker_engine_smoke.py` (local ignored verification utility).

## Scope and remaining acceptance work

The backend integration tests use real PostgreSQL 16, Redis 7, RQ payloads and
entrypoints, runner orchestration, leases, callback persistence and engine.
S3 is moto with the real S3 adapter; HTTP is FastAPI TestClient; Docker processes
are simulated in that suite. It covers upload/build, failed smoke, full games,
replay gzip metadata, duplicate delivery/lost HTTP response, crash, infra retry
and retained diagnostic logs. Docker execution is checked separately above.

Not verified here: one continuous deployed pipeline with real MinIO, registry,
forking RQ workers and browser; Linux C++ sandbox compilation; malicious bots;
production TLS/WireGuard/firewall/backup restore. P1/P2/viewer still contain
documentation rather than runnable frontend applications. dev-v1 is not an
approved official tournament ruleset.

Full backend suite passed, including the five new cross-component cases and
engine-version freeze regression. Initial integration-test failure was a test
adapter that did not reset simulated compiler output after the runner cleared
its log; the adapter was corrected before this successful full run.

Backend and contract tooling pin different JSON Schema versions. CI installs
contract requirements into `contracts/.deps`, preserving backend's frozen
dependencies. `uv pip check` confirms the restored backend environment is
compatible. GitHub-hosted CI itself has not been run or published from this task.
