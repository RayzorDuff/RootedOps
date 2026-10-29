#!/usr/bin/env bash
# CI: native PostgreSQL dump -> fresh generated project -> restore -> assertion.
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
SOURCE="commerce-restore-source-${RANDOM}"
cleanup() {
  docker rm -f -v "$SOURCE" >/dev/null 2>&1 || true
  if [[ -f "$WORK/env/compose.yml" ]]; then
    docker compose --env-file "$WORK/env/.env" -f "$WORK/env/compose.yml" down -v >/dev/null 2>&1 || true
  fi
  rm -rf "$WORK"
}
trap cleanup EXIT
# Refuse to touch an existing local test environment.
[[ -z "$(docker ps -aq --filter label=com.docker.compose.project=commerce-test)" ]]
[[ -z "$(docker volume ls -q --filter label=com.docker.compose.project=commerce-test)" ]]
python3 "$ROOT/scripts/commerce_staging.py" "$WORK/env"
docker compose --env-file "$WORK/env/.env" -f "$WORK/env/compose.yml" config --quiet
mkdir -p "$WORK/backup/db"
docker run -d --name "$SOURCE" -e POSTGRES_PASSWORD=synthetic-test-only postgres:16 >/dev/null
for i in $(seq 1 60); do
  if docker exec "$SOURCE" pg_isready -U postgres >/dev/null 2>&1; then break; fi
  [[ "$i" != 60 ]]
  sleep 2
done
docker exec "$SOURCE" psql -U postgres -v ON_ERROR_STOP=1 -c "CREATE TABLE restore_probe(id integer PRIMARY KEY, description text); INSERT INTO restore_probe VALUES(1, 'Synthetic restore fixture');" >/dev/null
docker exec "$SOURCE" pg_dump -U postgres --clean --if-exists --no-owner --no-privileges postgres | gzip > "$WORK/backup/db/mushroomprocess-bridge-postgres.sql.gz"
python3 "$ROOT/scripts/commerce_restore.py" "$WORK/env" "$WORK/backup" --components mushroomprocess
result="$(docker compose --env-file "$WORK/env/.env" -f "$WORK/env/compose.yml" exec -T mushroomprocess-bridge-postgres psql -U mushroomprocess_test -d mushroomprocess_test -Atc 'SELECT count(*) FROM restore_probe WHERE id=1')"
[[ "$result" == 1 ]]
# A second invocation must refuse before mutating the restored data.
if python3 "$ROOT/scripts/commerce_restore.py" "$WORK/env" "$WORK/backup" --components mushroomprocess; then exit 1; fi
printf '%s\n' 'Native PostgreSQL restore smoke test passed.'
