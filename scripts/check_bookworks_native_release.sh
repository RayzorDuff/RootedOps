#!/usr/bin/env bash
set -Eeuo pipefail
[[ $# -eq 1 && -f "$1/wordpress.json" ]] || { echo "Usage: bash scripts/check_bookworks_native_release.sh RELEASE_DIR" >&2; exit 2; }
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONTAINER="${BOOKWORKS_WORDPRESS_CONTAINER:-docker-rootedpsyche-wordpress-1}"
REMOTE="/tmp/bookworks-native-verify-$$"
trap 'sudo docker exec "$CONTAINER" rm -f "$REMOTE.json" "$REMOTE.php" >/dev/null 2>&1 || true' EXIT
sudo docker cp "$1/wordpress.json" "$CONTAINER:$REMOTE.json"
sudo docker cp "$ROOT/scripts/check_bookworks_native_release.php" "$CONTAINER:$REMOTE.php"
sudo docker exec "$CONTAINER" php "$REMOTE.php" "$REMOTE.json"
