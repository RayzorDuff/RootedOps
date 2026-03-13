#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
COMPOSE_FILE="$REPO_ROOT/deploy/docker/docker-compose.yml"
ENV_FILE="$REPO_ROOT/.env"

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 /path/to/backup-directory" >&2
  exit 1
fi

BACKUP_DIR="$(cd "$1" && pwd)"

if [[ ! -d "$BACKUP_DIR" ]]; then
  echo "Backup directory not found: $BACKUP_DIR" >&2
  exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

DOCKER_BIN="${DOCKER_BIN:-sudo docker}"
COMPOSE_SH=(sudo docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE")

log() {
  printf '[%s] %s\n' "$(date '+%F %T')" "$*"
}

restore_volume() {
  local volume_name="$1" archive_name="$2"
  local archive="$BACKUP_DIR/volumes/$archive_name"
  if [[ ! -f "$archive" ]]; then
    log "Skipping missing archive $archive"
    return 0
  fi
  log "Restoring volume $volume_name from $archive_name"
  $DOCKER_BIN volume create "$volume_name" >/dev/null
  $DOCKER_BIN run --rm \
    -v "$volume_name:/volume" \
    -v "$BACKUP_DIR/volumes:/backup:ro" \
    alpine:3.20 \
    sh -lc "rm -rf /volume/* /volume/.[!.]* /volume/..?* 2>/dev/null || true; cd /volume && tar -xzf /backup/$archive_name"
}

restore_bind_archive() {
  local archive_name="$1" target_parent="$2"
  local archive="$BACKUP_DIR/bind_mounts/$archive_name"
  if [[ ! -f "$archive" ]]; then
    log "Skipping missing archive $archive"
    return 0
  fi
  mkdir -p "$target_parent"
  log "Restoring bind archive $archive_name"
  tar -xzf "$archive" -C "$target_parent"
}

restore_postgres_dump() {
  local dump_file="$1" container="$2" user="$3" db="$4"
  local dump_path="$BACKUP_DIR/db/$dump_file"
  if [[ ! -f "$dump_path" ]]; then
    log "Skipping missing dump $dump_path"
    return 0
  fi
  log "Restoring Postgres dump $dump_file into $container/$db"
  gunzip -c "$dump_path" | $DOCKER_BIN exec -i -e PGPASSWORD="${5:-}" "$container" psql -U "$user" -d "$db"
}

log "Validating checksums if present"
if [[ -f "$BACKUP_DIR/SHA256SUMS" ]]; then
  (cd "$BACKUP_DIR" && sha256sum -c SHA256SUMS)
fi

log "Restoring non-database volumes"
restore_volume nocodb_data nocodb_data.tgz
restore_volume n8n_data n8n_data.tgz
restore_volume appsmith_stacks appsmith_stacks.tgz
restore_volume erpnext_sites erpnext_sites.tgz
restore_volume erpnext_apps erpnext_apps.tgz
restore_volume erpnext_logs erpnext_logs.tgz
restore_volume erpnext_redis_cache_data erpnext_redis_cache_data.tgz
restore_volume erpnext_redis_queue_data erpnext_redis_queue_data.tgz

log "Restoring bind-mounted content"
restore_bind_archive documenso-certs.tgz "$REPO_ROOT/deploy/documenso"
restore_bind_archive grav.tgz "$REPO_ROOT/deploy"
restore_bind_archive nginx.tgz "$REPO_ROOT/deploy"

log "Starting database containers only"
"${COMPOSE_SH[@]}" up -d signaturegate-postgres mushroomprocess-bridge-postgres nocodb-meta-postgres documenso-postgres erpnext-db

log "Waiting briefly for databases to become ready"
sleep 20

restore_postgres_dump signaturegate-postgres.sql.gz signaturegate-postgres "$SIG_DB_USER" "$SIG_DB_NAME" "$SIG_DB_PASSWORD"
restore_postgres_dump mushroomprocess-bridge-postgres.sql.gz mushroomprocess-bridge-postgres "$MP_BRIDGE_DB_USER" "$MP_BRIDGE_DB_NAME" "$MP_BRIDGE_DB_PASSWORD"
restore_postgres_dump nocodb-meta-postgres.sql.gz nocodb-meta-postgres "$NC_DB_USER" "$NC_DB_NAME" "$NC_DB_PASSWORD"
restore_postgres_dump documenso-postgres.sql.gz documenso-postgres "$DOCUMENSO_DB_USER" "$DOCUMENSO_DB_NAME" "$DOCUMENSO_DB_PASSWORD"

if [[ -f "$BACKUP_DIR/db/erpnext-all-databases.sql.gz" ]]; then
  log "Restoring MariaDB dump into erpnext-db"
  gunzip -c "$BACKUP_DIR/db/erpnext-all-databases.sql.gz" | \
    $DOCKER_BIN exec -i -e MARIADB_ROOT_PASSWORD="$ERPNEXT_DB_ROOT_PASSWORD" erpnext-db \
      sh -lc 'exec mariadb -uroot -p"$MARIADB_ROOT_PASSWORD"'
fi

log "Restore complete. Start the full stack with:"
echo "sudo docker compose --env-file $ENV_FILE -f $COMPOSE_FILE up -d"
