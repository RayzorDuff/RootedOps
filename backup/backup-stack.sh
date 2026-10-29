#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=volume-tools.sh
source "$SCRIPT_DIR/volume-tools.sh"
COMPOSE_FILE="$REPO_ROOT/docker/docker-compose.yml"
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
BACKUP_PREFIX="${BACKUP_PREFIX:-rootedops}"
LOCAL_STAGING_PARENT="${LOCAL_STAGING_PARENT:-/var/tmp/rootedops-backups}"
RCLONE_REMOTE="${RCLONE_REMOTE:-signaturegate-gdrive-free}"
REMOTE_BACKUP_ROOT="${REMOTE_BACKUP_ROOT:-${RCLONE_REMOTE}:SignatureGateBackups}"
REMOTE_PREFIX_PATH="${REMOTE_BACKUP_ROOT%/}/${BACKUP_PREFIX}"
DOCKER_BIN="${DOCKER_BIN:-sudo docker}"
# Optional explicit path to the rclone config used by unattended backups.
# Rclone may otherwise select a different config for each Unix user.
RCLONE_CONFIG_FILE="${RCLONE_CONFIG_FILE:-}"
COMPOSE_SH=(sudo docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE")
MINECRAFT_BEDROCK_DATA_PATH="${MINECRAFT_BEDROCK_DATA_PATH:-$REPO_ROOT/minecraft/bedrock}"
if [[ "$MINECRAFT_BEDROCK_DATA_PATH" != /* ]]; then
  MINECRAFT_BEDROCK_DATA_PATH="$REPO_ROOT/${MINECRAFT_BEDROCK_DATA_PATH#./}"
fi
MINECRAFT_BACKUP_STOP_CONTAINER="${MINECRAFT_BACKUP_STOP_CONTAINER:-true}"
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
# Scheduling containers are paused only during the cold volume snapshots.
# If archiving fails, resume them before removing the temporary staging directory.
PAUSED_CONTAINERS=()
resume_paused_containers() {
  local container
  for container in "${PAUSED_CONTAINERS[@]}"; do
    log "Restarting paused container $container"
    $DOCKER_BIN start "$container" >/dev/null || true
  done
  PAUSED_CONTAINERS=()
}
cleanup_and_resume() {
  resume_paused_containers
  cleanup
}
trap cleanup_and_resume EXIT

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

if [[ -n "$RCLONE_CONFIG_FILE" ]]; then
  if [[ ! -r "$RCLONE_CONFIG_FILE" ]]; then
    echo "Rclone configuration is not readable: $RCLONE_CONFIG_FILE" >&2
    exit 1
  fi
  export RCLONE_CONFIG="$RCLONE_CONFIG_FILE"
fi
REMOTE_NAME="${REMOTE_BACKUP_ROOT%%:*}"
if ! rclone listremotes | grep -Fxq "${REMOTE_NAME}:"; then
  echo "rclone remote ${REMOTE_NAME}: not found for user $(id -un)." >&2
  echo "Check: rclone config file; rclone listremotes; RCLONE_CONFIG_FILE in .env" >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR"/{db,volumes,bind_mounts,meta}

log "Writing metadata"
git -C "$REPO_ROOT" rev-parse HEAD > "$BACKUP_DIR/meta/git_commit.txt" 2>/dev/null || true
$DOCKER_BIN version > "$BACKUP_DIR/meta/docker-version.txt"
$DOCKER_BIN volume ls > "$BACKUP_DIR/meta/docker-volumes.txt"
$DOCKER_BIN ps -a > "$BACKUP_DIR/meta/docker-ps.txt"
$DOCKER_BIN image ls --digests --no-trunc > "$BACKUP_DIR/meta/docker-images.txt"
$DOCKER_BIN exec erpnext-backend bench version > "$BACKUP_DIR/meta/frappe-app-versions.txt"
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
  # Refuse missing sources: docker run -v would silently create an empty volume.
  $DOCKER_BIN volume inspect "$volume_name" >/dev/null
  log "Archiving volume $volume_name"
  mkdir -p "$BACKUP_DIR/volumes"
  $DOCKER_BIN run --rm \
    -v "$volume_name:/volume:ro" \
    -v "$BACKUP_DIR/volumes:/backup" \
    alpine:3.20 \
    sh -lc "cd /volume && tar -czf /backup/$archive_name --numeric-owner ."
  validate_managed_volume_archive "$BACKUP_DIR/volumes/$archive_name"
}

backup_mounted_volume() {
  local container="$1" destination="$2" archive_name="$3" actual_volume
  actual_volume="$(resolve_mounted_volume "$container" "$destination")"
  # n8n SQLite and Appsmith embedded MongoDB need cold snapshots.
  local paused=false
  if [[ "$container" == n8n || "$container" == appsmith ]] && container_is_running "$container"; then
    log "Stopping $container for a consistent application volume backup"
    $DOCKER_BIN stop "$container" >/dev/null
    PAUSED_CONTAINERS+=("$container")
    paused=true
  fi
  backup_volume "$actual_volume" "$archive_name"
  if [[ "$paused" == true ]]; then
    $DOCKER_BIN start "$container" >/dev/null
    # Remove only the container successfully restarted; EXIT retries on failure.
    local -a remaining=()
    local entry
    for entry in "${PAUSED_CONTAINERS[@]}"; do
      [[ "$entry" == "$container" ]] || remaining+=("$entry")
    done
    PAUSED_CONTAINERS=("${remaining[@]}")
  fi
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

container_is_running() {
  local container="$1"
  [[ "$($DOCKER_BIN inspect -f '{{.State.Running}}' "$container" 2>/dev/null || true)" == "true" ]]
}

backup_minecraft_bedrock() {
  local src="$1" archive_name="$2"
  local was_running=false

  if [[ ! -e "$src" ]]; then
    log "Skipping missing Minecraft Bedrock data path $src"
    return 0
  fi

  if [[ "$MINECRAFT_BACKUP_STOP_CONTAINER" == "true" ]] && container_is_running minecraft-bedwars; then
    was_running=true
    log "Stopping minecraft-bedwars for a consistent Bedrock world backup"
    "${COMPOSE_SH[@]}" stop minecraft-bedwars
  fi

  backup_bind_path "$src" "$archive_name"

  if [[ "$was_running" == "true" ]]; then
    log "Restarting minecraft-bedwars after backup"
    "${COMPOSE_SH[@]}" up -d minecraft-bedwars
  fi
}

pg_dump_container signaturegate-postgres "$SIG_DB_USER" "$SIG_DB_NAME" "$SIG_DB_PASSWORD" \
  "$BACKUP_DIR/db/signaturegate-postgres.sql.gz"
pg_dump_container mushroomprocess-bridge-postgres "$MP_BRIDGE_DB_USER" "$MP_BRIDGE_DB_NAME" "$MP_BRIDGE_DB_PASSWORD" \
  "$BACKUP_DIR/db/mushroomprocess-bridge-postgres.sql.gz"
pg_dump_container listmonk-postgres "$LISTMONK_DB_USER" "$LISTMONK_DB_NAME" "$LISTMONK_DB_PASSWORD" \
  "$BACKUP_DIR/db/listmonk-postgres.sql.gz"
pg_dump_container nocodb-meta-postgres "$NC_DB_USER" "$NC_DB_NAME" "$NC_DB_PASSWORD" \
  "$BACKUP_DIR/db/nocodb-meta-postgres.sql.gz"
pg_dump_container documenso-postgres "$DOCUMENSO_DB_USER" "$DOCUMENSO_DB_NAME" "$DOCUMENSO_DB_PASSWORD" \
  "$BACKUP_DIR/db/documenso-postgres.sql.gz"
mariadb_dump_all erpnext-db "$ERPNEXT_DB_ROOT_PASSWORD" "$BACKUP_DIR/db/erpnext-all-databases.sql.gz"
# WordPress is deployed with a separate Compose file but shares the default docker project.
mariadb_dump_all docker-rootedpsyche-wordpress-db-1 "$ROOTEDPSYCHE_WP_DB_ROOT_PASSWORD" "$BACKUP_DIR/db/rootedpsyche-wordpress-all-databases.sql.gz"

# Non-database Docker volumes needed for a practical restore.
backup_mounted_volume nocodb /usr/app/data nocodb_data.tgz
backup_mounted_volume n8n /home/node/.n8n n8n_data.tgz
backup_mounted_volume appsmith /appsmith-stacks appsmith_stacks.tgz
backup_mounted_volume erpnext-backend /home/frappe/frappe-bench/sites erpnext_sites.tgz
backup_mounted_volume erpnext-backend /home/frappe/frappe-bench/apps erpnext_apps.tgz
backup_mounted_volume erpnext-backend /home/frappe/frappe-bench/logs erpnext_logs.tgz
# The full WordPress HTML volume includes uploads, plugins, themes, and MU plugins.
backup_mounted_volume docker-rootedpsyche-wordpress-1 /var/www/html rootedpsyche-wordpress-html.tgz

# Usually disposable, but keeping them may help preserve in-flight state.
backup_mounted_volume erpnext-redis-cache /data erpnext_redis_cache_data.tgz
backup_mounted_volume erpnext-redis-queue /data erpnext_redis_queue_data.tgz


# Dedicated Compose projects created during the scheduling deployment:
# rootedops-scheduling (Tymeslot), rallly-selfhosted (Rallly).
# Cold volume archives protect embedded Postgres and Rallly's Garage metadata/data.
# We do not quietly create an empty backup for a missing, configured installation.
backup_scheduling() {
  local -a running=()
  local volume container
  local -a containers=(rootedops-tymeslot rallly-selfhosted-web-1 rallly-selfhosted-db-1 rallly-selfhosted-garage-1)
  local -a volumes=(
    rootedops-scheduling_tymeslot_data
    rootedops-scheduling_tymeslot_pg
    rallly-selfhosted_db-data
    rallly-selfhosted_garage-meta
    rallly-selfhosted_garage-data
  )
  local present=0
  for volume in "${volumes[@]}"; do
    if $DOCKER_BIN volume inspect "$volume" >/dev/null 2>&1; then
      present=$((present+1))
    fi
  done
  if [[ "$present" -eq 0 ]]; then
    log "Scheduling volumes not installed; skipping scheduling backup"
    return 0
  fi
  if [[ "$present" -ne "${#volumes[@]}" ]]; then
    echo "Scheduling volumes partially installed ($present/${#volumes[@]}); refusing incomplete backup" >&2
    return 1
  fi
  # Check whether each container is running before stopping; only resume those.
  for container in "${containers[@]}"; do
    if container_is_running "$container"; then
      running+=("$container")
    fi
  done
  for container in "${running[@]}"; do
    log "Pausing scheduling container $container for consistent volume archive"
    $DOCKER_BIN stop "$container" >/dev/null
    PAUSED_CONTAINERS+=("$container")
  done
  for volume in "${volumes[@]}"; do
    backup_volume "$volume" "$volume.tgz"
  done
  # The upstream setup-generated Rallly .env contains secrets needed to recover
  # OAuth, signing, Postgres and Garage; it is not in the RootedOps root .env.
  local rallly_env="$REPO_ROOT/docker/scheduling/rallly-selfhosted/.env"
  if [[ ! -f "$rallly_env" ]]; then
    echo "Rallly .env missing; refusing incomplete scheduling backup" >&2
    return 1
  fi
  # setup generates mode 600/root-owned credentials; read via Docker root helper
  # rather than relaxing permissions on host credentials.
  log "Archiving protected Rallly configuration"
  $DOCKER_BIN run --rm \
    -v "$rallly_env:/source/.env:ro" \
    -v "$BACKUP_DIR/bind_mounts:/backup" \
    alpine:3.20 \
    sh -lc 'cd /source && tar -czf /backup/rallly-selfhosted-env.tgz .env'
  cp "$REPO_ROOT/docker/scheduling/tymeslot.compose.yml" "$BACKUP_DIR/meta/tymeslot.compose.yml"
  log "Scheduling volumes and credentials captured"
  resume_paused_containers
}

backup_scheduling

# Repo bind mounts and config required for a full restore.
backup_bind_path "$REPO_ROOT/documenso/certs" documenso-certs.tgz
backup_bind_path "$REPO_ROOT/grav" grav.tgz
backup_bind_path "$REPO_ROOT/listmonk" listmonk.tgz
backup_bind_path "$REPO_ROOT/nginx" nginx.tgz
backup_bind_path "$REPO_ROOT/LINODE_SETUP.md" linode-setup-md.tgz
backup_minecraft_bedrock "$MINECRAFT_BEDROCK_DATA_PATH" minecraft-bedrock.tgz

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
    printf '%s\n' "${entries[@]}" | python3 -c '
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
' "$daily_cutoff" "$current_month_start"
  )

  if [[ ${#to_delete[@]} -eq 0 ]]; then
    log "No remote backups eligible for pruning"
    return 0
  fi

  for dir_name in "${to_delete[@]}"; do
    log "Pruning remote backup $dir_name"
    # Only expired snapshots in our own backup prefix are deleted permanently.
    # Never use rclone cleanup here: it empties unrelated Drive trash.
    rclone purge "$remote_prefix/$dir_name" --drive-use-trash=false
  done
}

# Verify the uploaded snapshot before applying any retention policy.
rclone check "$BACKUP_DIR/" "$REMOTE_PREFIX_PATH/$TIMESTAMP/" --one-way
if [[ "${SKIP_BACKUP_PRUNE:-false}" != true ]]; then
  prune_remote_backups "$REMOTE_PREFIX_PATH" "$KEEP_DAILY_DAYS"
fi

log "Backup complete: $REMOTE_PREFIX_PATH/$TIMESTAMP"
