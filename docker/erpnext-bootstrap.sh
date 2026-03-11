#!/usr/bin/env bash
set -euo pipefail

cd /home/frappe/frappe-bench

wait_for_file() {
  local path="$1"
  local seconds="${2:-300}"
  local waited=0
  while [ ! -e "$path" ]; do
    if [ "$waited" -ge "$seconds" ]; then
      echo "Timed out waiting for $path" >&2
      return 1
    fi
    sleep 2
    waited=$((waited + 2))
  done
}

echo "Waiting for MariaDB and Redis..."
wait-for-it -t 180 "${ERPNEXT_DB_HOST}:${ERPNEXT_DB_PORT}"
wait-for-it -t 180 "${ERPNEXT_REDIS_CACHE_HOST}:${ERPNEXT_REDIS_CACHE_PORT}"
wait-for-it -t 180 "${ERPNEXT_REDIS_QUEUE_HOST}:${ERPNEXT_REDIS_QUEUE_PORT}"

echo "Waiting for apps volume to be initialized..."
wait_for_file "apps/frappe"
wait_for_file "apps/erpnext"

echo "Waiting for common_site_config.json from configurator..."
wait_for_file "sites/common_site_config.json"

if [ ! -f "sites/${ERPNEXT_SITE_NAME}/site_config.json" ]; then
  echo "Creating ERPNext site ${ERPNEXT_SITE_NAME}..."
  bench new-site "${ERPNEXT_SITE_NAME}" \
    --no-mariadb-socket \
    --db-root-password "${ERPNEXT_DB_ROOT_PASSWORD}" \
    --admin-password "${ERPNEXT_ADMIN_PASSWORD}" \
    --install-app erpnext
else
  echo "Site ${ERPNEXT_SITE_NAME} already exists."
fi

if [ ! -d "apps/hrms" ]; then
  echo "Fetching HRMS app (${ERPNEXT_HRMS_BRANCH})..."
  bench get-app --branch "${ERPNEXT_HRMS_BRANCH}" hrms https://github.com/frappe/hrms
else
  echo "HRMS app already present in apps/."
fi

if ! bench --site "${ERPNEXT_SITE_NAME}" list-apps | grep -qx "hrms"; then
  echo "Installing HRMS on site ${ERPNEXT_SITE_NAME}..."
  bench --site "${ERPNEXT_SITE_NAME}" install-app hrms
else
  echo "HRMS already installed on ${ERPNEXT_SITE_NAME}."
fi

echo "Setting ERPNext host_name..."
bench --site "${ERPNEXT_SITE_NAME}" set-config host_name "${ERPNEXT_PUBLIC_URL}"

echo "Running migrate..."
bench --site "${ERPNEXT_SITE_NAME}" migrate

echo "ERPNext bootstrap completed successfully."
