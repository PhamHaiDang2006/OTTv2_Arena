# Resource isolation handoff — 2026-10-22

Changed runner `engine_verifier.py` and `sandbox.py` so compiler and smoke bot use
RUNNER_CPUSET_BUILD. Changed VPS2/local Compose to pin worker control processes
and registry to auxiliary CPUs, cap their CPU/RAM/PIDs, and split local match
queues. Preserved existing worker state volumes. Added check_resources.py,
tests, CI invocation, env examples and deployment/runbook instructions.

HTTP contract 1.3.0, engine 1.0.0, job/callback v1 and rules dev-v1 are unchanged.
Owner B; A consumes engine timing and C consumes worker callbacks. Deploy runner
image and Compose together; no database migration or frontend update required.

Verified from repository root using Python 3.12:

| Command/check | Actual result |
| --- | --- |
| `python -m unittest discover -s runner/tests -q` | 25 passed |
| `python -m unittest discover -s infra/tests -v` | 6 passed, including rendered VPS2/local Compose |
| Backend `pytest -q tests/test_runner_engine_integration.py tests/test_scrimmage_admission.py` | 10 passed using isolated PostgreSQL/Redis test services |
| `node contracts/build.mjs --check` | Passed |
| `python contracts/validate.py` | Passed: 88 definitions, 66 operations, 141 fixture cases |
| `python contracts/test_mock.py` | 5 passed |
| Compose `config --quiet`, VPS2 and merged local files | Passed |
| Local preflight against actual Docker host | Passed, budget 6.25 GiB |
| VPS2 preflight against this development Docker host | Correctly refused: 7.57 GiB available, 9.25 GiB required |
| Actual Docker smoke game using existing sample bot image | Completed; HostConfig confirmed CPU 2-3, quota 1 CPU, memory/swap both 512 MiB; test container cleaned up |
| PowerShell parser for start-local-play.ps1; `git diff --check` | Passed |

Compiler CPU arguments and cleanup were tested with a fake Docker client; a real
C++ compilation was not rerun. No production load benchmark or timing fairness
certification was performed. Full backend/web suites were not rerun because
their implementations were unchanged; relevant integration tests passed.

Existing running workers were not recreated, to avoid interrupting jobs; rebuild
the worker and follow RUNBOOK drain/upgrade steps before using the new allocation.
VPS2 defaults reserve logical CPUs 0-5 for tournament bots; auxiliary work shares
6-7. Local uses 0-1 and 2-3 respectively. Host Docker daemon, image packaging,
disk I/O and SMT contention still require operational monitoring; for strict
finals pause/drain build and scrimmage work. No commit, push or merge performed.
