#!/usr/bin/env bash
# Back up the live Rooted Psyche WordPress DB and wp-content without stopping containers.
set -Eeuo pipefail
umask 077
BACKUP_ROOT="${ROOTEDPSYCHE_WP_BACKUP_DIR:-/var/backups/rootedpsyche-wordpress}"
RETENTION_DAYS="${ROOTEDPSYCHE_WP_BACKUP_RETENTION_DAYS:-30}"
DB_CONTAINER="docker-rootedpsyche-wordpress-db-1"
WP_CONTAINER="docker-rootedpsyche-wordpress-1"
[[ "$RETENTION_DAYS" =~ ^[0-9]+$ ]] || { echo "Invalid retention days" >&2; exit 2; }
mkdir -p "$BACKUP_ROOT"
exec 9>"$BACKUP_ROOT/.backup.lock"
flock -n 9 || { echo "WordPress backup already running" >&2; exit 1; }
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
stage="$(mktemp -d "$BACKUP_ROOT/.pending-${stamp}-XXXXXX")"
trap 'rm -rf "$stage"' EXIT
for c in "$DB_CONTAINER" "$WP_CONTAINER"; do
  [[ "$(docker inspect -f '{{.State.Running}}' "$c")" == true ]] || { echo "$c is not running" >&2; exit 1; }
done
docker exec "$DB_CONTAINER" sh -c 'exec mariadb-dump -u root -p"$MARIADB_ROOT_PASSWORD" --single-transaction --quick --routines --triggers wordpress' > "$stage/wordpress.sql"
test -s "$stage/wordpress.sql"
grep -q 'MariaDB dump\|MySQL dump' "$stage/wordpress.sql" || { echo "SQL dump appears invalid" >&2; exit 1; }
docker cp "$WP_CONTAINER:/var/www/html/wp-content" "$stage/wp-content"
test -d "$stage/wp-content"
tar -C "$stage" -czf "$stage/wp-content.tar.gz" wp-content
rm -rf "$stage/wp-content"
sha256sum "$stage/wordpress.sql" "$stage/wp-content.tar.gz" > "$stage/SHA256SUMS"
( cd "$stage" && sha256sum -c SHA256SUMS )
final="$BACKUP_ROOT/$stamp"
mv "$stage" "$final"
trap - EXIT
echo "Verified WordPress backup: $final"
# Prune only timestamped backup directories, never partial or unrelated files.
find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d -regextype posix-extended -regex '.*/[0-9]{8}T[0-9]{6}Z' -mtime +"$RETENTION_DAYS" -exec rm -rf -- {} +
