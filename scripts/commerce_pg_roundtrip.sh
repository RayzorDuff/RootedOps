#!/usr/bin/env bash
# Disposable commerce-test PostgreSQL backup/restore verification only.
set -euo pipefail
config_dir="${1:?Usage: commerce_pg_roundtrip.sh /opt/commerce-test}"
project_name="$(docker compose --project-directory "$config_dir" --env-file "$config_dir/.env" -f "$config_dir/compose.yml" config --format json | python3 -c 'import json,sys; print(json.load(sys.stdin)["name"])')"
[ "$project_name" = commerce-test ] || { echo 'Refusing non-staging project' >&2; exit 1; }
docker compose --project-directory "$config_dir" --env-file "$config_dir/.env" -f "$config_dir/compose.yml" exec -T mushroomprocess-bridge-postgres sh -eu -c '
  umask 077
  [ "$POSTGRES_DB" = mushroomprocess_test ] || { echo "Refusing non-test database" >&2; exit 1; }
  pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f /tmp/commerce-roundtrip.dump
  createdb -U "$POSTGRES_USER" mushroomprocess_restorecheck
  pg_restore --exit-on-error -U "$POSTGRES_USER" -d mushroomprocess_restorecheck /tmp/commerce-roundtrip.dump
  psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d mushroomprocess_restorecheck -c "SELECT count(*) AS restored_catalog_rows FROM public.mp_ecommerce_catalog_inventory();"
'
echo 'Backup restored to mushroomprocess_restorecheck; source DB unchanged.'
