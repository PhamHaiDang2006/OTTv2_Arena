# Infrastructure and deployment

This folder owns the development data services, two VPS Compose deployments, Caddy, WireGuard templates, backup tooling, and operating runbook. Read the repository [AGENTS.md](../AGENTS.md), [integration contract](../integration.md) (especially sections 7–9), [architecture](../architecture.md), and [contracts/behavior.md](../contracts/behavior.md).

## Current implementation boundary

Backend, runner and engine implementations now exist. Build backend from
`backend/Dockerfile`, integrated workers from `runner/Dockerfile.engine`, and the
Python bot base from `engine/Dockerfile.bot` (all use repo-root build context).
VPS1 runs API and scheduler as separate services from the same backend image.
Web P1/P2/viewer are still documentation-only; full public deployment requires
those images. Publish/deploy images separately with immutable digests.
`dev-v1` remains development-only.

The dev MinIO service builds the upstream community source at a fixed commit because MinIO no longer publishes community binaries/images and its repository is archived. This is a convenience for local development, not a maintained or production-secure storage distribution. VPS1 requires a separately built and digest-pinned MinIO-compatible server and `mc` image; verify provenance, updates, and applicable AGPLv3 obligations before deployment.

Compose config validation checks YAML/interpolation only. It does not prove the app images exist, boot, migrate, expose the assumed ports, or satisfy API/SPA contracts. No production security claim is made: supply real secrets, TLS DNS, firewall/WireGuard setup, restricted S3 accounts, tested images, application rate limits, and a successful restore rehearsal first.

## Development services

### Windows: đăng ký và đăng nhập trên web local

Mở Docker Desktop, sau đó từ repo root chạy:

```powershell
powershell -ExecutionPolicy Bypass -File .\infra\start-local-api.ps1
```

Script tạo `infra/.env` với secret ngẫu nhiên nếu chưa có (không ghi đè), bật
PostgreSQL/Redis với volume bền, chạy migration và khởi động API nền tại 127.0.0.1:8000.
Yêu cầu đã cài backend/.venv theo backend/README.md. Log nằm ở
`infra/.local-api.error.log`, PID ở `infra/.local-api.pid`; các file này bị gitignore.
Chạy lại script khi mở máy; nếu API khỏe đang chạy thì dùng lại.

Mở terminal khác, `cd web`, `npm.cmd run dev`, vào http://127.0.0.1:5173/ để đăng ký.
Không chỉ chạy web: form cần API, PostgreSQL và Redis hoạt động.
Đây là startup cho API/tài khoản; nộp bot và chạy trận còn cần MinIO, registry,
scheduler và runner theo tài liệu từng phần. Không dùng database test cho tài khoản thật.

Commands below are run from `D:\Đại học\code\bruh\OTTv2_Arena\infra` in PowerShell, or from the equivalent repository `infra/` directory on Linux/macOS. Copy `.env.example` to `.env` and replace local placeholders. Do not commit `.env`.

```powershell
Copy-Item .env.example .env
docker compose --env-file .env -f docker-compose.dev.yml up --build -d
docker compose --env-file .env -f docker-compose.dev.yml ps
docker compose --env-file .env -f docker-compose.dev.yml logs -f postgres redis minio
docker compose --env-file .env -f docker-compose.dev.yml down
```

`down` preserves all named volumes; do not use `down -v` unless intentionally destroying local databases and objects. Before running backend directly on the host, override Docker-only service names in its process environment, for example:

```powershell
$env:DATABASE_URL = "postgresql+psycopg://ottv2:<URL-ENCODED-POSTGRES_PASSWORD>@localhost:5432/ottv2"
$env:REDIS_URL = "redis://:<URL-SAFE-REDIS_PASSWORD>@localhost:6379/0"
$env:S3_ENDPOINT_URL = "http://localhost:9000"
$env:S3_PUBLIC_ENDPOINT_URL = "http://localhost:9000"
```

Create the `ottv2` bucket and a separate least-privilege S3 account in MinIO at `http://localhost:9001`; never use a production root account as an application credential.

### Service/port map

| Compose file/service | Docker hostname | Container port | Host bind | Healthcheck | Durable volume |
| --- | --- | ---: | --- | --- | --- |
| `docker-compose.dev.yml` `postgres` | `postgres` | 5432 | `127.0.0.1:5432` (override with `POSTGRES_PORT`) | `pg_isready` against configured DB | `ottv2_dev_postgres_data` |
| `docker-compose.dev.yml` `redis` | `redis` | 6379 | `127.0.0.1:6379` (override with `REDIS_PORT`) | authenticated `redis-cli ping` | `ottv2_dev_redis_data` (AOF) |
| `docker-compose.dev.yml` `minio` API | `minio` | 9000 | `127.0.0.1:9000` (override with `MINIO_PORT`) | MinIO `/minio/health/ready` | `ottv2_dev_minio_data` |
| `docker-compose.dev.yml` `minio` console | `minio` | 9001 | `127.0.0.1:9001` (override with `MINIO_CONSOLE_PORT`) | Covered by MinIO API readiness | `ottv2_dev_minio_data` |
| `docker-compose.vps1.yml` `caddy` | `caddy` | 80, 443 TCP/UDP | public TCP 80/443 and UDP 443 | None configured; validate the Caddyfile and monitor public HTTP/TLS | `ottv2_vps1_caddy_data`, `ottv2_vps1_caddy_config` |
| `docker-compose.vps1.yml` `web-p1`, `web-p2` | `web-p1`, `web-p2` | 8080 | Internal Docker network only | None configured; app image health route is not yet defined | none |
| `docker-compose.vps1.yml` `backend` | `backend` | 8000 | `VPS1_WG_IP:8000` only, plus internal Docker network | None configured; backend readiness route is not yet defined | none |
| `docker-compose.vps1.yml` `postgres` | `postgres` | 5432 | Internal Docker network only | `pg_isready` | `ottv2_vps1_postgres_data` |
| `docker-compose.vps1.yml` `redis` | `redis` | 6379 | `VPS1_WG_IP:6379` only | Authenticated `redis-cli ping` | `ottv2_vps1_redis_data` (AOF) |
| `docker-compose.vps1.yml` `minio` API | `minio` | 9000 | `VPS1_WG_IP:9000` only | MinIO `/minio/health/ready` | `ottv2_vps1_minio_data` |
| `docker-compose.vps1.yml` `minio-backup` (opt-in profile) | `minio-backup` → `minio`, external S3 | No listener | No published port | One-shot mirror exit status; source MinIO health dependency | none |
| `docker-compose.vps2.yml` `registry` | `registry` | 5000 | `127.0.0.1:5000` only | None configured; monitor the registry `/v2/` endpoint | `ottv2_vps2_registry_data` |
| `docker-compose.vps2.yml` worker services | `build-worker`, `match-tournament-*`, `match-scrimmage-*` | Image-defined | No published ports | No Compose healthcheck; monitor app heartbeats/queue via backend | One callback-state volume per worker |

VPS1's database, Redis, MinIO, and backend host ports are bound only to its WireGuard address (except internal Docker-only PostgreSQL). Ensure WireGuard is up before starting that Compose stack. VPS2 has no public service port; its registry binds loopback. The registry uses HTTP on loopback and the VPS2 Docker daemon must be configured for that loopback registry. Protect VPS2 accordingly.

## VPS deployment

VPS2 keeps official games and scrimmages on separate workers (contract 1.3.0).
`match-tournament-1..3` listen only on `match:tournament` and pin bots to CPU
pairs `0/1`, `2/3`, `4/5`; `match-scrimmage-1` listens only on `match:scrimmage`
with pair `6/7`, so at most one scrimmage game runs at a time. Pairs are set
through `RUNNER_CPUSET_BLUE`/`RUNNER_CPUSET_RED` and need host CPU IDs 0–7. On a
smaller host, drop workers and adjust their pairs before deployment; do not run
multiple matches on the same pair, and do not point a tournament worker at the
scrimmage queue. These assignments isolate match bots from each other, but do
not reserve CPUs from the build worker or other host processes. The backend
pauses new scrimmages while tournament games are pending (`SCRIMMAGE_*` in
`vps1.env.example`); see RUNBOOK section 7 before switching a running VPS2 from
the earlier `match-worker-1..4` services.

Use separate host-specific secret files, not the development `.env.example`: copy `vps1.env.example` to `.env` on VPS1 and `vps2.env.example` to `.env` on VPS2. The VPS2 file contains only Redis/API/worker-scoped S3/registry secrets and the worker image reference—never `DATABASE_URL`, app S3 credentials, MinIO root credentials, or `JWT_SECRET`. Prefer URL-safe alphanumeric passwords, or percent-encode special characters in `DATABASE_URL` and `VPS2_REDIS_URL`. Do not copy secrets into a web build or any `VITE_*` variable.

All `replace-*` values, example IPs/domains, and digest strings are placeholders. Build application images outside Compose and set `VPS1_BACKEND_IMAGE`, `VPS1_P1_IMAGE`, `VPS1_P2_IMAGE`, `VPS1_MINIO_IMAGE`, `VPS1_MC_IMAGE`, and `VPS2_WORKER_IMAGE` to registry references pinned by real `sha256` digests. Build the integrated runner image from `runner/Dockerfile.engine`, publish it, and configure the VPS2 `OTTv2_ENGINE_FACTORY` and `OTTv2_BUILD_VERIFIER` values to system-owned adapters included in that image. Check that the backend listens on `0.0.0.0:8000`, both static servers listen on `8080`, P2 is built for `/admin/`, and both static servers provide SPA history fallback. Frontends may be built with `VITE_API_BASE_URL=/api/v1` and `VITE_WS_URL=wss://DOMAIN/ws`; these are public URLs, never secrets. The backend must implement the health/readiness and migration behavior agreed with C before using production images.

From `/srv/ottv2/infra` on VPS1:

```sh
cp vps1.env.example .env
chmod 600 .env
docker compose --env-file .env -f docker-compose.vps1.yml pull
docker compose --env-file .env -f docker-compose.vps1.yml up -d postgres redis minio
# Provision the application bucket and restricted S3 service account before the API.
# Run migrations once before API and scheduler:
docker compose --env-file .env -f docker-compose.vps1.yml run --rm --no-deps backend python -m app.cli migrate
docker compose --env-file .env -f docker-compose.vps1.yml up -d
```

The migration command above is provided by backend/Dockerfile and app.cli. Set up the VPN, DNS, firewall, MinIO accounts and database backup first. On VPS2, after WireGuard and the Docker daemon's local-registry configuration are ready:

```sh
cp vps2.env.example .env
chmod 600 .env
docker compose --env-file .env -f docker-compose.vps2.yml pull
docker compose --env-file .env -f docker-compose.vps2.yml up -d
docker compose --env-file .env -f docker-compose.vps2.yml logs -f build-worker match-tournament-1 match-tournament-2 match-tournament-3 match-scrimmage-1
```

See [RUNBOOK.md](RUNBOOK.md) for first-time provisioning, upgrades, backup/restore, monitoring, and incidents.

### Migrations, seed, and smoke tests

Build from repo root with `docker build -f backend/Dockerfile -t ottv2-backend:local .`.
From infra, migrate once with
`docker compose --env-file .env -f docker-compose.vps1.yml run --rm --no-deps backend python -m app.cli migrate`.
Then start API and scheduler. Never seed a live tournament with development data.
Development seed and test instructions are in [backend/README.md](../backend/README.md).

`docker-compose.test.yml` provides isolated, disposable PostgreSQL/Redis on
loopback ports 55432/56379. It has no persistent DB volume and must not be used
for participant data. The integration test uses moto for S3 and simulated Docker
processes; full MinIO/Docker/public frontend acceptance remains separate.

## Edge routing and operational constraints

- Caddy obtains TLS for `DOMAIN` and `STORAGE_DOMAIN`. `/` routes to P1, `/admin/` to P2, `/api/v1/*` and `/ws` to the backend. Caddy passes WebSocket upgrades through automatically. `S3_PUBLIC_ENDPOINT_URL` must be `https://STORAGE_DOMAIN` so signed browser URLs use a publicly resolvable host; backend/worker S3 endpoints stay private.
- `/internal`, `/internal/*`, `/api/v1/internal`, and `/api/v1/internal/*` return 404 at the public edge. Workers call `/api/v1/internal/*` directly through WireGuard and must still authenticate with `WORKER_API_TOKEN`.
- API and WebSocket routes are matched before the web catch-all, so an API 404 is never rewritten to an SPA page. Caddy proxies web routes to separately built static app images; those images must implement their own history fallback and P2 path prefix.
- Caddy's built-in request body cap is 2 MiB; backend ZIP validation remains authoritative at 1 MiB. Caddy does **not** ship a general rate-limit directive. Implement and test the contract's per-team submission and per-IP read rate limits in the backend or supply/review a Caddy build with a suitable module; this Compose stack does not claim to enforce those limits.
- Configure bucket CORS for the exact public frontend origin and required browser methods/headers. Compressed replay objects need `Content-Type: application/json` and `Content-Encoding: gzip`; configure object metadata at upload time and verify browser behavior instead of assuming the proxy will repair it.
- PostgreSQL/Redis/MinIO and backend private API exposure depends on correct WireGuard interface addresses and host firewall rules. Docker port publishing can interact with host firewalls; verify external TCP/UDP scans from outside both hosts.
- VPS2 workers mount `/var/run/docker.sock`; this is effectively root access to the VPS. Run only trusted, pinned worker images on the isolated VPS2, never mount the socket on VPS1, and allow no student-bot network access.
- The build worker starts its compiler container through the host daemon, so its work directory is bind-mounted at the identical path (`/var/lib/ottv2/work`) on the host and in the container. Do not move it to a container-only path such as a tmpfs, or C++ builds fail with `main.cpp: No such file or directory`.
- Local rehearsal: `runner/scripts/dev_e2e.py` runs the runner in-process; the full VPS2 Compose stack was also verified against the dev Redis/MinIO with a local registry (Python and C++ build, then a match). Shell scripts must keep LF line endings; `.gitattributes` enforces this.

## Validation

From `infra/`, validate config against the provided placeholder env files:

```sh
docker compose --env-file .env.example -f docker-compose.dev.yml config --quiet
docker compose --env-file vps1.env.example -f docker-compose.vps1.yml config --quiet
docker compose --env-file vps2.env.example -f docker-compose.vps2.yml config --quiet
```

These checks require Docker Compose v2 and validate Compose parsing/interpolation only. Starting the services, production networking, application behavior, migrations, TLS, API/WS routing, signed URL browser access, backup synchronization, restore, and security controls require live dependencies and the missing product images; they are not claimed as tested by this folder.
