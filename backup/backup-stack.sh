#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
COMPOSE_FILE="$REPO_ROOT/deploy/docker/docker-compose.yml"
ENV_FILE="$REPO_ROOT/.env"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_PREFIX="${BACKUP_PREFIX:-signaturegate}"
LOCAL_STAGING_PARENT="${LOCAL_STAGING_PARENT:-/var/tmp/signaturegate-backups}"
RCLONE_REMOTE="${RCLONE_REMOTE:-signaturegate-gdrive}"
REMOTE_BACKUP_ROOT="${REMOTE_BACKUP_ROOT:-${RCLONE_REMOTE}:SignatureGateBackups}"
REMOTE_PREFIX_PATH="${REMOTE_BACKUP_ROOT%/}/${BACKUP_PREFIX}"
DOCKER_BIN="${DOCKER_BIN:-sudo docker}"
KEEP_DAILY_DAYS="${KEEP_DAILY_DAYS:-7}"

mkdir -p "$LOCAL_STAGING_PARENT"
LOCAL_STAGE_ROOT="$(mktemp -d "$LOCAL_STAGING_PARENT/${BACKUP_PREFIX}-${TIMESTAMP}-XXXXXX")"
BACKUP_DIR="$LOCAL_STAGE_ROOT/$TIMESTAMP"
LATEST_LINK="$LOCAL_STAGE_ROOT/latest"

cleanup() {
  if [[ -n "${LOCAL_STAGE_ROOT:-}" && -d "$LOCAL_STAGE_ROOT" ]]; then
    rm -rf "$LOCAL_STAGE_ROOT"
  fi
}
trap cleanup EXIT

log() {
  printf '[%s] %s\n' "$(date '+%F %T')" "$*"
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Missing required command: $1" >&2
    exit 1
  }
}

require_cmd bash
require_cmd date
require_cmd find
require_cmd gzip
require_cmd mktemp
require_cmd python3
require_cmd rclone
require_cmd sha256sum
require_cmd tar

mkdir -p "$BACKUP_DIR"/{db,volumes,bind_mounts,meta}

log "Writing metadata"
git -C "$REPO_ROOT" rev-parse HEAD > "$BACKUP_DIR/meta/git_commit.txt" 2>/dev/null || true
$DOCKER_BIN version > "$BACKUP_DIR/meta/docker-version.txt"
$DOCKER_BIN volume ls > "$BACKUP_DIR/meta/docker-volumes.txt"
$DOCKER_BIN ps -a > "$BACKUP_DIR/meta/docker-ps.txt"
cp "$COMPOSE_FILE" "$BACKUP_DIR/meta/docker-compose.yml"
cp "$ENV_FILE" "$BACKUP_DIR/meta/.env"

pg_dump_container() {
  local container="$1" user="$2" db="$3" password="$4" outfile="$5"
  log "Dumping Postgres database $db from $container"
  $DOCKER_BIN exec -e PGPASSWORD="$password" "$container" \
    pg_dump -U "$user" -d "$db" --clean --if-exists --no-owner --no-privileges \
    | gzip -c > "$outfile"
}

mariadb_dump_all() {
  local container="$1" root_password="$2" outfile="$3"
  log "Dumping MariaDB databases from $container"
  $DOCKER_BIN exec -e MARIADB_ROOT_PASSWORD="$root_password" "$container" \
    sh -lc 'exec mariadb-dump -uroot -p"$MARIADB_ROOT_PASSWORD" --all-databases --single-transaction --quick --routines --triggers --events' \
    | gzip -c > "$outfile"
}

backup_volume() {
  local volume_name="$1" archive_name="$2"
  log "Archiving volume $volume_name"
  mkdir -p "$BACKUP_DIR/volumes"
  $DOCKER_BIN run --rm \
    -v "$volume_name:/volume:ro" \
    -v "$BACKUP_DIR/volumes:/backup" \
    alpine:3.20 \
    sh -lc "cd /volume && tar -czf /backup/$archive_name --numeric-owner ."
}

backup_bind_path() {
  local src="$1" archive_name="$2"
  log "Archiving bind path $src"
  mkdir -p "$BACKUP_DIR/bind_mounts"
  if [[ -e "$src" ]]; then
    tar -czf "$BACKUP_DIR/bind_mounts/$archive_name" -C "$(dirname "$src")" "$(basename "$src")"
  else
    log "Skipping missing path $src"
  fi
}

pg_dump_container signaturegate-postgres "$SIG_DB_USER" "$SIG_DB_NAME" "$SIG_DB_PASSWORD" \
  "$BACKUP_DIR/db/signaturegate-postgres.sql.gz"
pg_dump_container mushroomprocess-bridge-postgres "$MP_BRIDGE_DB_USER" "$MP_BRIDGE_DB_NAME" "$MP_BRIDGE_DB_PASSWORD" \
  "$BACKUP_DIR/db/mushroomprocess-bridge-postgres.sql.gz"
pg_dump_container nocodb-meta-postgres "$NC_DB_USER" "$NC_DB_NAME" "$NC_DB_PASSWORD" \
  "$BACKUP_DIR/db/nocodb-meta-postgres.sql.gz"
pg_dump_container documenso-postgres "$DOCUMENSO_DB_USER" "$DOCUMENSO_DB_NAME" "$DOCUMENSO_DB_PASSWORD" \
  "$BACKUP_DIR/db/documenso-postgres.sql.gz"
mariadb_dump_all erpnext-db "$ERPNEXT_DB_ROOT_PASSWORD" "$BACKUP_DIR/db/erpnext-all-databases.sql.gz"

# Non-database Docker volumes needed for a practical restore.
backup_volume nocodb_data nocodb_data.tgz
backup_volume n8n_data n8n_data.tgz
backup_volume appsmith_stacks appsmith_stacks.tgz
backup_volume erpnext_sites erpnext_sites.tgz
backup_volume erpnext_apps erpnext_apps.tgz
backup_volume erpnext_logs erpnext_logs.tgz

# Usually disposable, but keeping them may help preserve in-flight state.
backup_volume erpnext_redis_cache_data erpnext_redis_cache_data.tgz
backup_volume erpnext_redis_queue_data erpnext_redis_queue_data.tgz

# Repo bind mounts and config required for a full restore.
backup_bind_path "$REPO_ROOT/deploy/documenso/certs" documenso-certs.tgz
backup_bind_path "$REPO_ROOT/deploy/grav" grav.tgz
backup_bind_path "$REPO_ROOT/deploy/nginx" nginx.tgz
backup_bind_path "$REPO_ROOT/deploy/LINODE_SETUP.md" linode-setup-md.tgz

(
  cd "$BACKUP_DIR"
  find . -type f ! -name 'SHA256SUMS' -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS
)

ln -sfn "$TIMESTAMP" "$LATEST_LINK"

log "Syncing staged backup to $REMOTE_PREFIX_PATH"
rclone mkdir "$REMOTE_PREFIX_PATH"
rclone copy --links "$LOCAL_STAGE_ROOT/" "$REMOTE_PREFIX_PATH/"

prune_remote_backups() {
  local remote_prefix="$1"
  local keep_daily_days="$2"

  log "Applying retention policy to $remote_prefix"

  local now_epoch daily_cutoff current_month_start
  now_epoch="$(date +%s)"
  daily_cutoff="$((now_epoch - keep_daily_days * 86400))"
  current_month_start="$(date -d "$(date +%Y-%m-01) 00:00:00" +%s)"

  local -a entries=()
  while IFS= read -r entry; do
    entry="${entry%/}"
    [[ "$entry" =~ ^[0-9]{8}-[0-9]{6}$ ]] || continue
    entries+=("$entry")
  done < <(rclone lsf "$remote_prefix/" --dirs-only)

  if [[ ${#entries[@]} -eq 0 ]]; then
    log "No remote backup directories found for pruning"
    return 0
  fi

  mapfile -t to_delete < <(
    printf '%s\n' "${entries[@]}" | python3 - "$daily_cutoff" "$current_month_start" <<'PY'
import datetime as dt
import sys

daily_cutoff = int(sys.argv[1])
current_month_start = int(sys.argv[2])
entries = [line.strip() for line in sys.stdin if line.strip()]
parsed = []
for name in entries:
    ts = dt.datetime.strptime(name, "%Y%m%d-%H%M%S")
    parsed.append((name, int(ts.timestamp()), ts))
parsed.sort(key=lambda x: x[1])
keep = set()
weekly = {}
monthly = {}
for name, epoch, ts in parsed:
    if epoch >= daily_cutoff:
      keep.add(name)
    elif epoch >= current_month_start:
      weekly[(ts.isocalendar().year, ts.isocalendar().week)] = name
    else:
      monthly[(ts.year, ts.month)] = name
keep.update(weekly.values())
keep.update(monthly.values())
for name, _, _ in parsed:
    if name not in keep:
      print(name)
PY
  )

  if [[ ${#to_delete[@]} -eq 0 ]]; then
    log "No remote backups eligible for pruning"
    return 0
  fi

  for dir_name in "${to_delete[@]}"; do
    log "Pruning remote backup $dir_name"
    rclone purge "$remote_prefix/$dir_name"
  done
}

prune_remote_backups "$REMOTE_PREFIX_PATH" "$KEEP_DAILY_DAYS"

log "Backup complete: $REMOTE_PREFIX_PATH/$TIMESTAMP"
