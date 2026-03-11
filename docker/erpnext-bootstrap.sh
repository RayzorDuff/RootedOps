#!/usr/bin/env bash
set -euo pipefail

SITE_NAME="${ERPNEXT_SITE_NAME:-frontend}"
PUBLIC_URL="${ERPNEXT_PUBLIC_URL:-}"
HRMS_BRANCH="${ERPNEXT_HRMS_BRANCH:-version-16}"

wait-for-it -t 180 "${ERPNEXT_DB_HOST:-erpnext-db}:${ERPNEXT_DB_PORT:-3306}"
wait-for-it -t 180 "${ERPNEXT_REDIS_CACHE_HOST:-erpnext-redis-cache}:${ERPNEXT_REDIS_CACHE_PORT:-6379}"
wait-for-it -t 180 "${ERPNEXT_REDIS_QUEUE_HOST:-erpnext-redis-queue}:${ERPNEXT_REDIS_QUEUE_PORT:-6379}"

start=$(date +%s)
until [ -f sites/common_site_config.json ] \
  && jq -e '.db_host and .redis_cache and .redis_queue' sites/common_site_config.json >/dev/null 2>&1; do
  echo "Waiting for sites/common_site_config.json to be configured..."
  sleep 5
  if (( $(date +%s) - start > 180 )); then
    echo "Timed out waiting for ERPNext common_site_config.json"
    exit 1
  fi
done

if ! bench --site "$SITE_NAME" list-apps >/dev/null 2>&1; then
  echo "Creating ERPNext site: $SITE_NAME"
  bench new-site "$SITE_NAME" \
    --no-mariadb-socket \
    --mariadb-root-password "${ERPNEXT_DB_ROOT_PASSWORD}" \
    --admin-password "${ERPNEXT_ADMIN_PASSWORD}" \
    --db-root-username root \
    --install-app erpnext \
    --set-default
else
  echo "ERPNext site already exists: $SITE_NAME"
fi

if [ ! -d apps/hrms ]; then
  echo "Fetching HRMS app (${HRMS_BRANCH})"
  bench get-app --branch "$HRMS_BRANCH" https://github.com/frappe/hrms.git
else
  echo "HRMS app source already present"
fi

if ! bench --site "$SITE_NAME" list-apps | grep -qx 'hrms'; then
  echo "Installing HRMS on site: $SITE_NAME"
  bench --site "$SITE_NAME" install-app hrms
else
  echo "HRMS already installed on site: $SITE_NAME"
fi

if [ -n "$PUBLIC_URL" ]; then
  echo "Setting ERPNext host_name to $PUBLIC_URL"
  bench --site "$SITE_NAME" set-config host_name "$PUBLIC_URL"
fi

echo "Running final migrate for $SITE_NAME"
bench --site "$SITE_NAME" migrate

echo "ERPNext bootstrap complete"
