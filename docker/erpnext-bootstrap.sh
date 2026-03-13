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

ensure_common_site_config_value() {
  local key="$1"
  local raw_value="$2"
  local json_path="sites/common_site_config.json"

  python3 - "$json_path" "$key" "$raw_value" <<'PY'
import json, pathlib, sys
path = pathlib.Path(sys.argv[1])
key = sys.argv[2]
raw = sys.argv[3]
obj = {}
if path.exists():
    obj = json.loads(path.read_text())
try:
    value = int(raw)
except ValueError:
    value = raw
if obj.get(key) != value:
    obj[key] = value
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")
    print(f"Set {key} in {path} to {value!r}")
else:
    print(f"{key} already present in {path}: {value!r}")
PY
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

echo "Ensuring required Frappe settings exist in common_site_config.json..."
ensure_common_site_config_value db_host "${ERPNEXT_DB_HOST}"
ensure_common_site_config_value db_port "${ERPNEXT_DB_PORT}"
ensure_common_site_config_value redis_cache "redis://${ERPNEXT_REDIS_CACHE_HOST}:${ERPNEXT_REDIS_CACHE_PORT}"
ensure_common_site_config_value redis_queue "redis://${ERPNEXT_REDIS_QUEUE_HOST}:${ERPNEXT_REDIS_QUEUE_PORT}"
ensure_common_site_config_value redis_socketio "redis://${ERPNEXT_REDIS_QUEUE_HOST}:${ERPNEXT_REDIS_QUEUE_PORT}"
ensure_common_site_config_value socketio_port "${ERPNEXT_SOCKETIO_PORT:-9000}"

echo "Writing canonical sites/apps.txt..."
cat > sites/apps.txt <<'EOF'
frappe
erpnext
hrms
EOF

if [ ! -f "sites/${ERPNEXT_SITE_NAME}/site_config.json" ]; then
  echo "Creating ERPNext site ${ERPNEXT_SITE_NAME}..."
  bench new-site "${ERPNEXT_SITE_NAME}" \
    --mariadb-user-host-login-scope='%' \
    --db-root-password "${ERPNEXT_DB_ROOT_PASSWORD}" \
    --admin-password "${ERPNEXT_ADMIN_PASSWORD}" \
    --install-app erpnext
else
  echo "Site ${ERPNEXT_SITE_NAME} already exists."
fi

if [ ! -d "apps/hrms" ]; then
  echo "ERROR: apps/hrms is missing from the built ERPNext image." >&2
  exit 1
fi

if [ -f "sites/apps.txt" ] && ! grep -qx 'hrms' sites/apps.txt; then
  echo "Registering hrms in sites/apps.txt..."
  printf 'hrms\n' >> sites/apps.txt
fi

ensure_common_site_config_value socketio_port "${ERPNEXT_SOCKETIO_PORT:-9000}"

echo "Installing HRMS on site ${ERPNEXT_SITE_NAME}..."
bench --site "${ERPNEXT_SITE_NAME}" install-app hrms || true

echo "Verifying HRMS install..."
bench --site "${ERPNEXT_SITE_NAME}" mariadb -e "select app_name from \`tabInstalled Applications\` where app_name='hrms';" | grep -q hrms \
  && echo "HRMS installed." \
  || { echo "HRMS install did not complete cleanly."; exit 1; }

echo "Setting ERPNext host_name..."
bench --site "${ERPNEXT_SITE_NAME}" set-config host_name "${ERPNEXT_PUBLIC_URL}"

echo "Running migrate..."
bench --site "${ERPNEXT_SITE_NAME}" migrate

echo "ERPNext bootstrap completed successfully."