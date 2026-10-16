#!/usr/bin/env bash
set -Eeuo pipefail

INFRA_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
ENV_FILE="${INFRA_DIR}/.env"
BACKUP_DIR="${POSTGRES_BACKUP_DIR:-${INFRA_DIR}/backups/postgres}"

if [[ ! -f "${ENV_FILE}" ]]; then
  printf 'Missing %s; copy .env.example to .env and configure secrets first.\n' "${ENV_FILE}" >&2
  exit 2
fi
if [[ ! -d "${BACKUP_DIR}" ]]; then
  mkdir -p -- "${BACKUP_DIR}"
fi
chmod 700 -- "${BACKUP_DIR}"

stamp="$(date -u +'%Y%m%dT%H%M%SZ')"
filename="ottv2-${stamp}.dump"
destination="${BACKUP_DIR}/${filename}"
partial="${BACKUP_DIR}/.${filename}.partial.$$"
if [[ -e "${destination}" || -e "${partial}" ]]; then
  printf 'Refusing to overwrite an existing backup path: %s\n' "${destination}" >&2
  exit 2
fi
trap 'rm -f -- "${partial}"' EXIT

docker compose --project-directory "${INFRA_DIR}" \
  --env-file "${ENV_FILE}" \
  -f "${INFRA_DIR}/docker-compose.vps1.yml" \
  exec -T postgres sh -ec \
  'exec pg_dump --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" --format=custom --no-owner --no-acl' \
  > "${partial}"

if [[ ! -s "${partial}" ]]; then
  printf 'pg_dump returned an empty archive; keeping no backup.\n' >&2
  exit 1
fi
chmod 600 -- "${partial}"
mv -- "${partial}" "${destination}"
trap - EXIT
printf 'Created %s (%s bytes)\n' "${destination}" "$(wc -c < "${destination}")"

# Keep only the newest 48 hourly-format archives. Deletion is limited to
# regular files with the exact generated filename shape in this backup folder.
mapfile -t stale_files < <(
  find "${BACKUP_DIR}" -maxdepth 1 -type f \
    -name 'ottv2-????????T??????Z.dump' -printf '%f\n' |
    LC_ALL=C sort -r |
    tail -n +49
)
for stale_name in "${stale_files[@]}"; do
  if [[ "${stale_name}" =~ ^ottv2-[0-9]{8}T[0-9]{6}Z\.dump$ ]]; then
    stale_path="${BACKUP_DIR}/${stale_name}"
    if [[ -f "${stale_path}" && ! -L "${stale_path}" ]]; then
      rm -- "${stale_path}"
    fi
  fi
done
