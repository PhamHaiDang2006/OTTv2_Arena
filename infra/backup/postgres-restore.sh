#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  printf 'Usage: %s BACKUP.dump --target-db NEW_DATABASE --confirm-target-db NEW_DATABASE\n' "$0" >&2
}

if [[ "$#" -ne 5 || "$2" != "--target-db" || "$4" != "--confirm-target-db" ]]; then
  usage
  exit 2
fi
backup_file="$1"
target_db="$3"
confirmed_db="$5"
if [[ ! -f "${backup_file}" || -L "${backup_file}" || "${backup_file}" != *.dump ]]; then
  printf 'Backup must be an existing regular .dump file, not a symlink: %s\n' "${backup_file}" >&2
  exit 2
fi
if [[ ! "${target_db}" =~ ^[A-Za-z0-9_]{1,63}$ || "${target_db}" != "${confirmed_db}" ]]; then
  printf 'Target must be an explicit PostgreSQL identifier and match both target arguments.\n' >&2
  exit 2
fi

INFRA_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
ENV_FILE="${INFRA_DIR}/.env"
if [[ ! -f "${ENV_FILE}" ]]; then
  printf 'Missing %s; copy .env.example to .env and configure secrets first.\n' "${ENV_FILE}" >&2
  exit 2
fi
compose=(
  docker compose --project-directory "${INFRA_DIR}"
  --env-file "${ENV_FILE}"
  -f "${INFRA_DIR}/docker-compose.vps1.yml"
)
configured_db="$("${compose[@]}" exec -T postgres sh -ec 'printf "%s" "$POSTGRES_DB"')"
if [[ "${target_db}" == "${configured_db}" || "${target_db}" == "postgres" || "${target_db}" == "template0" || "${target_db}" == "template1" ]]; then
  printf 'Refusing to restore into the configured/live or a PostgreSQL system database (%s).\n' "${target_db}" >&2
  exit 2
fi

exists="$("${compose[@]}" exec -T postgres sh -ec \
  'target="$1"; psql --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" --tuples-only --no-align --set ON_ERROR_STOP=1 --command "SELECT 1 FROM pg_database WHERE datname = '\''$target'\''"' \
  sh "${target_db}")"
if [[ "${exists}" == "1" ]]; then
  printf 'Target database already exists. Restore only creates a new database and never drops/cleans one: %s\n' "${target_db}" >&2
  exit 2
fi

printf 'Creating new database %s and restoring %s. Existing databases will not be changed.\n' \
  "${target_db}" "${backup_file}"
"${compose[@]}" exec -T postgres sh -ec \
  'target="$1"; psql --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" --set ON_ERROR_STOP=1 --command "CREATE DATABASE \"$target\""' \
  sh "${target_db}"
"${compose[@]}" exec -T postgres sh -ec \
  'target="$1"; exec pg_restore --exit-on-error --no-owner --no-acl --username="$POSTGRES_USER" --dbname="$target"' \
  sh "${target_db}" < "${backup_file}"
printf 'Restore finished in %s. Verify the new DB before any application cutover.\n' "${target_db}"
