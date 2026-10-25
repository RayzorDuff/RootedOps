#!/usr/bin/env bash
# Approved native WordPress fundraising release: check, publish, rollback.
set -Eeuo pipefail
usage(){ echo "Usage: bash scripts/promote_bookworks_native.sh --release DIR --mode check|promote|rollback [--to-sha SHA256]" >&2; exit 2; }
RELEASE="" MODE="" TO_SHA=""
while (($#)); do
 case "$1" in
  --release) RELEASE="${2:-}"; shift 2;;
  --mode) MODE="${2:-}"; shift 2;;
  --to-sha) TO_SHA="${2:-}"; shift 2;;
  *) usage;;
 esac
done
[[ -d "$RELEASE" && "$MODE" =~ ^(check|promote|rollback)$ ]] || usage
if [[ "$MODE" == rollback ]]; then [[ "$TO_SHA" =~ ^[a-f0-9]{64}$ ]] || usage; else [[ -z "$TO_SHA" ]] || usage; TO_SHA="-"; fi
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RELEASE="$(realpath "$RELEASE")"
# The native release validator must succeed before any WordPress mutation.
bash "$ROOT/scripts/deploy_bookworks_artifact.sh" --release "$RELEASE" --mode check
# Ensure current page, hash, identity and presentation assets are intact.
bash "$ROOT/scripts/check_bookworks_native_release.sh" "$RELEASE"
CONTAINER="${BOOKWORKS_WORDPRESS_CONTAINER:-docker-rootedpsyche-wordpress-1}"
REMOTE="/tmp/bookworks-native-promote-$$"
trap 'sudo docker exec "$CONTAINER" rm -f "$REMOTE.json" "$REMOTE.php" >/dev/null 2>&1 || true' EXIT
sudo docker cp "$RELEASE/wordpress.json" "$CONTAINER:$REMOTE.json"
sudo docker cp "$ROOT/scripts/promote_bookworks_native.php" "$CONTAINER:$REMOTE.php"
sudo docker exec "$CONTAINER" php "$REMOTE.php" "$REMOTE.json" "$MODE" "$TO_SHA"
