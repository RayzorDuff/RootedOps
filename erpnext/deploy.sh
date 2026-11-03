#!/usr/bin/env bash
set -Eeuo pipefail

# Deploy the version-controlled RootedOps ERPNext custom app into the shared
# erpnext_apps Docker volume, then migrate, clear cache, restart the Python
# processes, and verify that the runtime source matches the repository.
#
# Run on the ERPNext host from anywhere inside the RootedOps repository:
#   ./erpnext/deploy.sh
#
# Optional site / app selection:
#   ./erpnext/deploy.sh erp.danks.store commerce
#   ./erpnext/deploy.sh erp.danks.store both

usage() {
  cat <<'USAGE'
Usage: erpnext/deploy.sh [site] [payroll|commerce|both]
       erpnext/deploy.sh [payroll|commerce|both]
       erpnext/deploy.sh [--site SITE] [--app payroll|commerce|both]
       erpnext/deploy.sh --help
Aliases: rootedops_payroll, rootedops_commerce
Defaults: site=erp.danks.store, app=payroll
USAGE
}
normalize_app() {
  case "$1" in
    payroll|rootedops_payroll) echo payroll ;;
    commerce|rootedops_commerce) echo commerce ;;
    both) echo both ;;
    *) return 1 ;;
  esac
}
SITE=erp.danks.store
SELECTION=payroll
site_set=false
app_set=false
while (($#)); do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    --site)
      (($# >= 2)) && [[ -n "$2" ]] || { usage >&2; exit 2; }
      "$site_set" && { echo "ERROR: site specified twice." >&2; exit 2; }
      SITE="$2"; site_set=true; shift 2 ;;
    --app)
      (($# >= 2)) && [[ -n "$2" ]] || { usage >&2; exit 2; }
      "$app_set" && { echo "ERROR: app specified twice." >&2; exit 2; }
      SELECTION="$(normalize_app "$2")" || { usage >&2; exit 2; }
      app_set=true; shift 2 ;;
    -*) echo "ERROR: Unknown option: $1" >&2; usage >&2; exit 2 ;;
    *)
      if normalized="$(normalize_app "$1")"; then
        "$app_set" && { echo "ERROR: app specified twice." >&2; exit 2; }
        SELECTION="$normalized"; app_set=true
      else
        "$site_set" && { echo "ERROR: site specified twice." >&2; exit 2; }
        SITE="$1"; site_set=true
      fi
      shift ;;
  esac
done
case "$SELECTION" in
  payroll) APPS=(rootedops_payroll) ;;
  commerce) APPS=(rootedops_commerce) ;;
  both) APPS=(rootedops_payroll rootedops_commerce) ;;
esac
REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
COMPOSE=(sudo docker compose --env-file ./.env -f docker/docker-compose.yml)
BACKEND=erpnext-backend

log() {
  printf '\n=== %s ===\n' "$1"
}

die() {
  echo "ERROR: $*" >&2
  exit 1
}

trap 'echo "ERROR: deployment failed at line $LINENO." >&2' ERR

[[ -f .env ]] || die "Missing .env in $REPO_ROOT."
[[ -f docker/docker-compose.yml ]] || die "Missing docker/docker-compose.yml."
[[ "$(git branch --show-current)" == "main" ]] || die "Deployment must run from the main branch."

log "Repository"
echo "Repository: $REPO_ROOT"
echo "Before:    $(git rev-parse --short HEAD)"

log "Update repository"
git pull --ff-only origin main

LOCAL_HEAD="$(git rev-parse HEAD)"
REMOTE_HEAD="$(git rev-parse origin/main)"
[[ "$LOCAL_HEAD" == "$REMOTE_HEAD" ]] || die "Local main is not identical to origin/main."

echo "Commit:    $(git rev-parse --short HEAD)"
echo "Message:   $(git log -1 --pretty=%s)"

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "WARNING: tracked local modifications are present."
  echo "         They will NOT be deployed; deployment uses committed HEAD."
fi

if [[ -n "$(git ls-files --others --exclude-standard)" ]]; then
  echo "WARNING: untracked files are present."
  echo "         They are ignored by this deployment."
fi

log "Validate Docker Compose"
"${COMPOSE[@]}" config >/dev/null

log "Check ERPNext backend"
sudo docker inspect "$BACKEND" --format '{{if .State.Running}}running{{else}}not-running{{end}}' |
  grep -qx running ||
  die "$BACKEND is not running."

log "Check selected installed apps and package availability"
for APP_NAME in "${APPS[@]}"; do
  APP_SOURCE="$REPO_ROOT/erpnext/apps/$APP_NAME"
  [[ -d "$APP_SOURCE" ]] || die "Missing source: $APP_SOURCE"
  installed_apps="$("${COMPOSE[@]}" exec -T "$BACKEND" bench --site "$SITE" list-apps)" ||
    die "Cannot list installed apps on site $SITE."
  printf '%s\n' "$installed_apps" | grep -Eq "^$APP_NAME([[:space:]]|$)" ||
    die "$APP_NAME is not installed on $SITE; this script updates only installed apps."
  # All ERPNext services share the built image. Check imports in fresh image
  # before any copy/restart; a pip install in only the running backend is not durable.
  IMAGE="$(sudo docker inspect "$BACKEND" --format '{{.Config.Image}}')"
  if [[ "$APP_NAME" == "rootedops_commerce" ]]; then
    sudo docker run --rm --entrypoint /bin/sh "$IMAGE" -c \
      'python -c "import flit_core, rootedops_commerce"' ||
      die "Commerce/flit_core missing from image; build and deploy a reviewed persistent image first."
  fi
done

log "Deploy selected RootedOps app sources"
for APP_NAME in "${APPS[@]}"; do
  APP_SOURCE="$REPO_ROOT/erpnext/apps/$APP_NAME"
  APP_TARGET="/home/frappe/frappe-bench/apps/$APP_NAME"
  # Copy only committed files; do not include local caches or untracked files.
  git archive --format=tar HEAD "erpnext/apps/$APP_NAME" |
    sudo docker exec -i -u 0 "$BACKEND" tar -xf - -C "$APP_TARGET" --strip-components=3
  sudo docker exec -u 0 "$BACKEND" chown -R frappe:frappe "$APP_TARGET"
  while IFS= read -r -d '' rel; do
    host_hash="$(sha256sum "$REPO_ROOT/$rel" | awk '{print $1}')"
    container_rel="${rel#erpnext/apps/$APP_NAME/}"
    container_hash="$(sudo docker exec "$BACKEND" sha256sum "$APP_TARGET/$container_rel" | awk '{print $1}')"
    [[ "$host_hash" == "$container_hash" ]] ||
      die "Source mismatch after copy: $rel"
  done < <(git ls-files -z "erpnext/apps/$APP_NAME")
  echo "All tracked $APP_NAME files match the container."
done

log "Run ERPNext migration"
"${COMPOSE[@]}" exec -T "$BACKEND" \
  bench --site "$SITE" migrate

log "Clear Frappe cache"
"${COMPOSE[@]}" exec -T "$BACKEND" \
  bench --site "$SITE" clear-cache

log "Restart ERPNext application services"
"${COMPOSE[@]}" restart \
  "$BACKEND" \
  erpnext-queue-short \
  erpnext-queue-long \
  erpnext-scheduler \
  erpnext-websocket

# Restart the frontend after backend/websocket so nginx resolves live upstreams
# after an application deployment. This avoids transient/stale 502s when the
# backend or Socket.IO service has just been restarted.
"${COMPOSE[@]}" restart erpnext-frontend

log "Verify services"
for service in \
  "$BACKEND" \
  erpnext-queue-short \
  erpnext-queue-long \
  erpnext-scheduler \
  erpnext-websocket \
  erpnext-frontend
do
  state="$(sudo docker inspect "$service" --format '{{if .State.Running}}running{{else}}not-running{{end}}')"
  [[ "$state" == "running" ]] || die "$service is not running after restart."
  echo "$service: $state"
done

log "Verify runtime source after restart"
for APP_NAME in "${APPS[@]}"; do
  APP_TARGET="/home/frappe/frappe-bench/apps/$APP_NAME"
  while IFS= read -r -d '' rel; do
    host_hash="$(sha256sum "$REPO_ROOT/$rel" | awk '{print $1}')"
    container_rel="${rel#erpnext/apps/$APP_NAME/}"
    container_hash="$(sudo docker exec "$BACKEND" sha256sum "$APP_TARGET/$container_rel" | awk '{print $1}')"
    [[ "$host_hash" == "$container_hash" ]] ||
      die "Runtime source mismatch after restart: $rel"
  done < <(git ls-files -z "erpnext/apps/$APP_NAME")
  echo "Runtime $APP_NAME source matches committed files."
done

log "Deployment complete"
echo "Commit: $LOCAL_HEAD"
echo "Site:   $SITE"
echo "Apps:   ${APPS[*]}"
