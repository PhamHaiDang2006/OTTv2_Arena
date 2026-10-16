# Runner and infra handoff messages

Ready-to-send messages for A (engine), C (backend) and the contract owner.

---

## Message to A (engine owner)

**Subject: Engine adapter and build verifier for the OTTv2 runner**

Hi A,

The runner and infra are done and tested with a stand-in engine. I need two things from you to replace it with the real engine. Nothing else in the runner changes.

**1. Engine factory.** Set `OTTv2_ENGINE_FACTORY=your_module:make_engine`. `make_engine()` takes no arguments and returns an object with:

```python
async def run_game(self, blue_io, red_io, config) -> dict
```

- `blue_io` and `red_io` are the bot handles:
  - `await bot.send_line(text)`
  - `await bot.read_line(timeout_ms)` raises `TimeoutError` or `EOFError` on a timeout or exit
  - `await bot.close()`
- `config` is the contract `config` block: engine_version, ruleset_id, map_id, initial_fen, players, budget_ms, init_ms, grace_ms, hard_timeout_extra_ms, max_turns and seed.
- Return `winner`, `reason`, `plies`, `duration_ms` and `replay`, with the `replay` result matching the `GameResult`. The runner rejects a mismatch.
- **Forfeit rules are yours.** If `run_game` raises an exception, the runner reports `infra_error` with no result. So bot timeouts, crashes, illegal moves and protocol errors must be turned into a normal `GameResult` inside your engine. I tested this with bots that crash and hang mid-match, and both ended as `infra_error`.

**2. Build verifier.** Set `OTTv2_BUILD_VERIFIER=your_module:make_build_verifier`. The returned object has `verify(image, job, timeout_seconds) -> None`. It should play a real smoke game against a system-owned opponent, and raise `BotBuildError` (from `ottv2_runner.errors`) if the bot fails.

**Reference:** `runner/ottv2_runner/devkit.py` has a working stand-in that you can copy. It plays no real rules and must not be used for a tournament.

**Bot line protocol:** `OTTV2 1`, `READY <name>`, `INIT ...`, `OK`, `STATE ...`, `GO`, `MOVE ...`, `END ...`. Lines starting with `#` are debug.

**How to test your adapter** (needs Docker, plus the dev stack from `infra/docker-compose.dev.yml`):

```powershell
cd runner
$env:OTTv2_ENGINE_FACTORY = "your_module:make_engine"
$env:OTTv2_BUILD_VERIFIER = "your_module:make_build_verifier"
python scripts\dev_e2e.py
```

`dev_e2e.py` currently sets those two variables to the stand-in, so please change that part. Its match checks should pass with your engine. The stand-in's score is fixed at BLUE wins, so some assertions may need adjusting for your rules.

**Questions for you:**
1. Does `run_game` need anything beyond the config above?
2. Is the replay format final?

Thanks!

---

## Message to C (backend owner)

**Subject: Runner jobs and callbacks that the backend must implement**

Hi C,

The runner takes jobs from Redis queues and reports back over HTTP. This is what I need on your side.

**1. Enqueue jobs with RQ on the shared Redis:**
- `ottv2_runner.jobs.build_submission` on the `build` queue
- `ottv2_runner.jobs.run_match` on `match:tournament` or `match:scrimmage`

Payloads follow the contract. The key fields:
- **Build:** `schema_version, job_id, submission_id, language (python or cpp), source_key, source_sha256, engine_version`.
- **Match:** `schema_version, job_id, game_id, attempt, blue_image, red_image, map_id, engine_version, players, config`.

The `config` values are fixed by validation: `budget_ms=60000`, `init_ms=10000`, `grace_ms=50`, `hard_timeout_extra_ms=1000`, `max_turns=300`. Anything else is rejected.

**2. Serve these internal endpoints under `INTERNAL_API_BASE_URL`, which must end in `/api/v1`:**
- `POST /internal/builds/{submission_id}`
- `POST /internal/games/{game_id}`
- `POST /internal/workers/heartbeat`

**3. Auth and headers.** Every call carries `Authorization: Bearer <WORKER_API_TOKEN>` and, for job callbacks, `X-Worker-Lease: <lease token>`. Use the lease token to reject stale callbacks.

**4. Statuses the runner sends.**
- **Build:** `building`, then `ready`, `failed` or `infra_error`. On `ready`, `image_tag` is an immutable `registry/ottv2-bot@sha256:…` reference. Store it unchanged, and pass it back in match jobs as `blue_image` and `red_image`. `build_log_key` points at the build log in storage.
- **Match:** `running`, then `finished` or `infra_error`. On `finished`, `replay_key` is the replay object and `log_key` is a slash-terminated prefix that holds the replay and four `.log` files.

**5. Response behaviour:**
- **2xx:** accepted.
- **409:** the runner treats it as a stale or duplicate callback and drops it. Return it when the lease token is not current.
- **5xx or network errors:** the runner retries forever, so the worker blocks until you are back.
- **Other 4xx:** the runner treats it as a fatal error that needs an operator. Don't return this for transient problems.

Terminal results are also written to a durable outbox. After an outage, an operator runs `ottv2-runner flush-outbox` on VPS2, and the stored results are delivered without rebuilding.

**6. Please confirm:**
- The exact migration command for your pinned backend image. The infra README assumes `alembic upgrade head`.
- The backend and web image digests, for `vps1.env`.
- That staging objects are moved to their final location by your finalization step.

**How to check your side:** `runner/scripts/dev_e2e.py` includes a fake backend that shows the exact calls the runner makes.

Thanks!

---

## Message to the contract owner

For bots that fail the build handshake, the runner currently reports a `failed` build. Please confirm `COMPILE_ERROR` is the right error code.
