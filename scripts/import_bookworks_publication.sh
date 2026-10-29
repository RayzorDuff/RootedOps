#!/usr/bin/env bash
# Stage a BookWorks JSON publication payload into WordPress; never auto-publish.
set -Eeuo pipefail
if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "Usage: $0 /path/to/bookworks-publication.json [dry-run|draft]" >&2
  exit 2
fi
PAYLOAD="$(realpath "$1")"
MODE="${2:-dry-run}"
[[ "$MODE" == dry-run || "$MODE" == draft ]] || { echo "Mode must be dry-run or draft" >&2; exit 2; }
[[ -f "$PAYLOAD" ]] || { echo "Missing payload: $PAYLOAD" >&2; exit 2; }
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONTAINER="docker-rootedpsyche-wordpress-1"
REMOTE="/tmp/bookworks-import-$$.json"
cleanup() { sudo docker exec "$CONTAINER" rm -f "$REMOTE" >/dev/null 2>&1 || true; }
trap cleanup EXIT
sudo docker cp "$PAYLOAD" "$CONTAINER:$REMOTE"
sudo docker cp "$ROOT/scripts/import_bookworks_publication.php" "$CONTAINER:/tmp/import_bookworks_publication.php"
sudo docker exec "$CONTAINER" php /tmp/import_bookworks_publication.php "$REMOTE" "$MODE"
