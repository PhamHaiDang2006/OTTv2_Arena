# Operations runbook

This is an operational template, not evidence that the product stack is production-ready. Backend/engine/runner Dockerfiles now exist; web product images remain unimplemented. Confirm image ports, migrations, readiness routes, callback persistence, and object-storage policy with their owners before a real rollout. Do not run an official tournament on `dev-v1`; it is an unconfirmed development ruleset.

## 1. First-time preparation

1. Provision two Linux hosts with separate deployment users, SSH keys only, current OS updates, and Docker Engine/Compose v2. VPS1 should expose only TCP 22 (restricted to operator IPs), TCP 80/443, and UDP WireGuard `51820` publicly. VPS2 should expose only restricted TCP 22 publicly; do not publish its registry or worker ports outside loopback.
2. Install WireGuard tools on both hosts. Generate one key pair per host locally with `wg genkey`/`wg pubkey`; keep private keys outside the repository and in the host secret store. Fill the commented `PrivateKey` and `PublicKey` fields in `wireguard/vps1.conf.example` and `vps2.conf.example` locally, set VPS2's peer endpoint to the real VPS1 public IP/port, install as `/etc/wireguard/wg0.conf` with mode `0600`, then enable/start `wg-quick@wg0`. Ensure addresses match `VPS1_WG_IP` and `VPS2_WG_IP`. Do not commit completed configs.
3. Allow UDP 51820 at the VPS1 endpoint. Verify `wg show` reports a recent handshake and each peer can reach the other's tunnel address. Configure the host firewall and provider firewall; Docker-published ports can bypass simplistic firewall assumptions.
4. Point `DOMAIN` and `STORAGE_DOMAIN` DNS A/AAAA records to VPS1. Ensure both names resolve publicly before Caddy starts. Make `STORAGE_DOMAIN` match the public signed-URL host configured in the backend.
5. Build and push backend, P1, P2, worker, MinIO, and MinIO Client (`mc`) images outside Compose. Pin all deployed images by immutable digest in host-specific `.env` files. No application-image build is defined here. Confirm backend `0.0.0.0:8000`, static servers `0.0.0.0:8080`, P1 base `/`, P2 base `/admin/`, WebSocket `/ws`, and backend migration/health commands. The MinIO community source is archived; its local development build is a fixed source snapshot, not a recommended production binary. Verify your selected image provenance, maintenance, and AGPLv3 obligations.
6. Create host-specific secrets. Use `vps1.env.example` only as VPS1's `.env` and `vps2.env.example` only as VPS2's `.env`; protect each file (mode `0600`). The worker host must never receive database credentials, app S3 credentials, MinIO root credentials, or `JWT_SECRET`. The worker token must match on both hosts. Set strong, unique PostgreSQL, Redis, MinIO root, app S3, worker S3, mirror-source, backup-destination, JWT and worker-token secrets in a secret manager and only the appropriate host `.env`. Use URL-safe alphanumeric passwords or correctly URL-encode password characters in connection URLs.
7. Provision MinIO bucket `S3_BUCKET` and distinct least-privilege S3 accounts for the backend, VPS2 workers, and mirror source (read/list only). Keep worker S3 credentials only on VPS2; neither VPS1's backend nor the web images need them. Do not give application or worker containers MinIO root credentials. Provision a separate external backup bucket and key with write/list access only to the backup prefix. Configure bucket CORS for the exact browser origin and required GET/HEAD response headers. Compressed replays must be uploaded with `Content-Type: application/json` and `Content-Encoding: gzip`. Configure external lifecycle/versioning/retention. `mc mirror` is a synchronization copy, not an immutable backup by itself.
8. On VPS2 configure Docker daemon access to the `127.0.0.1:5000` HTTP registry endpoint (loopback only), if the selected worker build/push implementation needs it. Confirm the image tag/digest workflow with runner owners. The worker socket mount is effectively host-root; keep VPS2 isolated and never reuse it for the public API.

## 2. Start and verify

Use `infra/` as the working directory on each host. On VPS1:

```sh
docker compose --env-file .env -f docker-compose.vps1.yml config --quiet
docker compose --env-file .env -f docker-compose.vps1.yml pull
docker compose --env-file .env -f docker-compose.vps1.yml up -d postgres redis minio
docker compose --env-file .env -f docker-compose.vps1.yml ps
```

Provision the bucket/accounts before starting the backend. Run `docker compose --env-file .env -f docker-compose.vps1.yml run --rm --no-deps backend python -m app.cli migrate` once, before the API and scheduler services. Then:

```sh
docker compose --env-file .env -f docker-compose.vps1.yml up -d
docker compose --env-file .env -f docker-compose.vps1.yml ps
docker compose --env-file .env -f docker-compose.vps1.yml logs --tail=100 caddy backend scheduler
```

On VPS2, after WireGuard and registry access are verified:

```sh
docker compose --env-file .env -f docker-compose.vps2.yml config --quiet
docker compose --env-file .env -f docker-compose.vps2.yml pull
docker compose --env-file .env -f docker-compose.vps2.yml up -d
docker compose --env-file .env -f docker-compose.vps2.yml ps
```

Acceptance checks before admitting traffic: inspect all health states; verify public P1 and P2 direct/deep links; verify `/api/v1` and `/ws`; verify public `/api/v1/internal/*` and `/internal/*` return 404; verify a worker callback succeeds only from the VPN with its token; verify signed object URLs load in a real browser with correct content type/encoding; verify UDP/TCP exposure from an external network. These app-level tests cannot currently pass until the product components exist.

## 3. Routine commands and monitoring

```sh
docker compose --env-file .env -f docker-compose.vps1.yml ps
docker compose --env-file .env -f docker-compose.vps1.yml logs --since=15m caddy backend postgres redis minio
docker compose --env-file .env -f docker-compose.vps2.yml ps
docker compose --env-file .env -f docker-compose.vps2.yml logs --since=15m build-worker match-worker-1 match-worker-2 match-worker-3 match-worker-4
docker stats --no-stream
df -h
wg show
```

Use the backend's admin queue/worker heartbeat view once implemented. Alert on queued work >50, `INFRA_ERROR` >2%, disk free <20%, worker heartbeat >5 minutes, backend sustained 5xx, and callback-pending backlog >5 minutes. Check both hosts' system time, service health, Caddy certificate renewal, Docker disk usage, MinIO capacity, and external signed-URL reachability. The current stack has no metrics/alerting agent; alerts must be connected to an independent monitor. Caddy does not implement the contract's rate limits; backend enforcement is mandatory. Don't equate Compose's database/Redis/MinIO health checks with API readiness.

## 4. PostgreSQL backups and restore rehearsal

The backup script writes a custom-format dump under `infra/backups/postgres`, sets private permissions, and retains at most the 48 newest files matching its exact timestamped `ottv2-*.dump` name. Run it once per hour on VPS1 (systemd timer preferred; an hourly cron is an alternative):

```cron
0 * * * * cd /srv/ottv2/infra && bash backup/postgres-backup.sh >> /var/log/ottv2-postgres-backup.log 2>&1
```

Verify each run succeeded and copy the backup out of the VPS1 failure domain to encrypted, access-controlled offsite storage. A local volume alone is not a backup. Protect the offsite copy and test retention/restore policy.

Restore always creates a **new, explicitly named database**. It refuses the configured live database, PostgreSQL system databases, an existing target database, and symlink/non-`.dump` input; it never uses `pg_restore --clean`, `DROP DATABASE`, or automatic cleanup. A failed restore may leave a partial new database; inspect it and decide any separately authorized cleanup manually. From `infra/`:

```sh
bash backup/postgres-restore.sh backups/postgres/ottv2-YYYYMMDDTHHMMSSZ.dump \
  --target-db ottv2_restore_rehearsal --confirm-target-db ottv2_restore_rehearsal
```

Use a non-production target and run a rehearsal at least before go-live and after major schema/image upgrades. Validate row counts, key records, migrations, app connectivity against the new DB, and recovery time. Do not change `DATABASE_URL` or perform production cutover until the restored DB is verified and an operator approves. Restore does not stop services, replace the live database, or remove a rehearsal DB.

## 5. MinIO offsite synchronization

On VPS1, schedule this once daily after provisioning source/destination accounts:

```sh
docker compose --env-file .env -f docker-compose.vps1.yml --profile backup run --rm minio-backup
```

The one-shot `mc mirror --overwrite` copies the configured source bucket to the external bucket/prefix and does not use `--remove`; source deletions do not delete backup objects. Review exit status/logs and monitor destination capacity. Set external bucket versioning/retention and verify objects can be read back; synchronize a large bucket initially before relying on daily deltas. Use credentials scoped to the source bucket and external backup prefix only. An example 02:30 UTC cron on VPS1:

```cron
30 2 * * * cd /srv/ottv2/infra && docker compose --env-file .env -f docker-compose.vps1.yml --profile backup run --rm minio-backup >> /var/log/ottv2-minio-backup.log 2>&1
```

## 6. Upgrades and rollback

1. Review release notes and compatibility; confirm immutable image digests and migration order with backend/runner/web owners. Preserve the old digests.
2. Run a PostgreSQL backup and confirm offsite storage. Verify MinIO mirror age and VPS1/VPS2 free disk.
3. Pull the pinned images. Run any one-time backward-compatible database migration using the image owner's confirmed command; never run an unverified guessed migration entrypoint.
4. Update one host at a time. VPS1 API/web change first only if compatible with the existing worker protocol; then VPS2 workers. Do not restart all four match workers at once during live games unless the backend lease/retry behavior is confirmed.
5. Verify health, API/WS, deep links, internal-route isolation, signed URLs, callbacks, queue latency, worker heartbeat, and logs. For a failed release, restore previous image digests. Database rollback is not automatic: follow the migration owner's documented recovery plan and restore into a new DB, not over the live database.

## 7. Incident procedures

### VPS2 down / no worker heartbeat

Confirm `wg show`, host/daemon status, disk and worker logs. Preserve Docker/worker state and callback-pending volumes; do not delete containers, bot images, or state directories as an initial response. Restore VPS2 or a replacement from pinned worker images and secrets. Backend lease expiry/watchdog should mark lost work `infra_error` and create a new attempt; verify this behavior in staging first. Do not manually replay a job or alter game rows. Reconcile pending callbacks/attempts through the backend before re-enabling competition.

### Disk full

Identify consumers with `df -h`, `docker system df`, and per-volume inspection. Pause new work through the supported backend queue controls if available. Preserve PostgreSQL, MinIO, Caddy certificates, registry and worker callback state. Move/copy verified backups off host before removing only known expired backup archives or unreferenced cache data with an approved scoped command. Never run broad `docker system prune --volumes`, `rm -rf`, or delete a named volume to make space. Resume only after free space and alerts are healthy.

### Queue stuck / callback backlog

Check Redis health/auth, WireGuard route, API availability, worker heartbeat, lease age, worker logs, and MinIO reachability. Pause enqueueing using backend admin controls if safe; do not flush Redis or reset leases manually. Worker callbacks must retry the persisted result, not rerun the game on HTTP timeout. Resolve the failing dependency, then resume workers and confirm each job's terminal/current attempt state in the backend.

### Backend/API errors or storage URL failures

Check Caddy and backend logs without printing tokens, cookies, signed URLs, source, or secrets. Check PostgreSQL/Redis/MinIO readiness and disk. Confirm `S3_PUBLIC_ENDPOINT_URL` host is reachable from browsers and matches the host used to sign URLs; check TLS, MIME/content-encoding, and CORS. Internal callbacks remain reachable only through WireGuard. Roll back the app image if needed; do not bypass auth or publish MinIO/Redis to the Internet.

### Rerun a game

Use the authorized admin API/UI only after verifying the game's current attempt, reason, tournament freeze/downstream state, and relevant logs. The contract creates a new `game_id`/attempt and preserves history; do not enqueue a raw Redis job, edit DB rows, overwrite replay keys, or delete the old result. Confirm whether the round can be reopened before action. Keep the audit record and validate the new current attempt before resuming the round.

### Applying the CPU/RAM isolation update

1. Pause `build`, `match:tournament`, and `match:scrimmage` via P2. Wait until running jobs finish and pending callbacks are delivered. Pausing queues alone does not kill running jobs.
2. Build the updated runner image outside production Compose, pin its digest, and update the environment from vps2.env.example. Keep all existing state volumes. Local `match-worker` retains its name/volume and switches to tournament-only; the new scrimmage worker gets a new volume.
3. Run `python infra/check_resources.py --env-file infra/.env -f infra/docker-compose.vps2.yml` from the repository root on the destination Docker host. The default layout needs 8 logical CPUs and a 9.25 GiB budget (12 GiB recommended). Never bypass a failed preflight by overlapping tournament and auxiliary CPU sets.
4. Recreate workers/registry using Compose, verify worker heartbeats and container CPU/RAM settings, then resume the queues. For local rehearsal, start-local-play.ps1 runs the local preflight and starts both dedicated match workers.
5. Inspect sibling bot/compiler containers as well as workers: they use the host daemon, so their limits are separate. Build image assembly/pull/push and OS/SMT/disk contention are not eliminated by container CPU pinning. Pause build and scrimmage queues and let in-flight work drain before a timing-sensitive final.
