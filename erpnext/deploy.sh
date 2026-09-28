#!/usr/bin/env bash
set -Eeuo pipefail

# Deploy the version-controlled RootedOps ERPNext custom app into the shared
# erpnext_apps Docker volume, then migrate, clear cache, restart the Python
# processes, and verify that the runtime source matches the repository.
#
# Run on the ERPNext host from anywhere inside the RootedOps repository:
#   ./erpnext/deploy.sh
#
# Optional site override:
#   ./erpnext/deploy.sh erp.danks.store

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "$REPO_ROOT" ]]; then
  echo "ERROR: Run this script from inside the RootedOps Git repository." >&2
  exit 1
fi

cd "$REPO_ROOT"

SITE="${1:-erp.danks.store}"
COMPOSE=(sudo docker compose --env-file ./.env -f docker/docker-compose.yml)
BACKEND="erpnext-backend"
APP_NAME="rootedops_payroll"
APP_SOURCE="$REPO_ROOT/erpnext/apps/$APP_NAME"
APP_TARGET="/home/frappe/frappe-bench/apps/$APP_NAME"

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
[[ -d "$APP_SOURCE" ]] || die "Missing ERPNext app source: $APP_SOURCE."
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

log "Deploy ERPNext custom app"
sudo docker cp \
  "$APP_SOURCE/." \
  "$BACKEND:$APP_TARGET/"

log "Verify deployed source"
while IFS= read -r -d '' rel; do
  host_hash="$(sha256sum "$REPO_ROOT/$rel" | awk '{print $1}')"
  container_rel="${rel#erpnext/apps/$APP_NAME/}"
  container_hash="$(
    sudo docker exec "$BACKEND" sha256sum "$APP_TARGET/$container_rel" |
      awk '{print $1}'
  )"
  [[ "$host_hash" == "$container_hash" ]] ||
    die "Source mismatch after copy: $rel"
done < <(git ls-files -z "erpnext/apps/$APP_NAME")

echo "All tracked $APP_NAME files match the container."

log "Run ERPNext migration"
"${COMPOSE[@]}" exec -T "$BACKEND" \
  bench --site "$SITE" migrate

log "Clear Frappe cache"
"${COMPOSE[@]}" exec -T "$BACKEND" \
  bench --site "$SITE" clear-cache

log "Restart ERPNext Python services"
"${COMPOSE[@]}" restart \
  "$BACKEND" \
  erpnext-queue-short \
  erpnext-queue-long \
  erpnext-scheduler

log "Verify services"
for service in "$BACKEND" erpnext-queue-short erpnext-queue-long erpnext-scheduler; do
  state="$(sudo docker inspect "$service" --format '{{if .State.Running}}running{{else}}not-running{{end}}')"
  [[ "$state" == "running" ]] || die "$service is not running after restart."
  echo "$service: $state"
done

log "Verify runtime source after restart"
while IFS= read -r -d '' rel; do
  host_hash="$(sha256sum "$REPO_ROOT/$rel" | awk '{print $1}')"
  container_rel="${rel#erpnext/apps/$APP_NAME/}"
  container_hash="$(
    sudo docker exec "$BACKEND" sha256sum "$APP_TARGET/$container_rel" |
      awk '{print $1}'
  )"
  [[ "$host_hash" == "$container_hash" ]] ||
    die "Runtime source mismatch after restart: $rel"
done < <(git ls-files -z "erpnext/apps/$APP_NAME")

echo "Runtime $APP_NAME source matches committed repository files."

log "Deployment complete"
echo "Commit: $LOCAL_HEAD"
echo "Site:   $SITE"
echo "App:    $APP_NAME"
