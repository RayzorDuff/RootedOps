#!/usr/bin/env bash
# Explicit promotion/rollback of checksum-approved original BookWorks HTML.
set -Eeuo pipefail
usage(){ echo "Usage: bash scripts/promote_bookworks_original_html.sh --release ABSOLUTE_DIR --mode check|promote|rollback" >&2; exit 2; }
RELEASE="" MODE=""
while (($#)); do
 case "$1" in
  --release) RELEASE="${2:-}"; shift 2;;
  --mode) MODE="${2:-}"; shift 2;;
  *) usage;;
 esac
done
[[ -n "$RELEASE" && -d "$RELEASE" && "$RELEASE" = /* ]] || usage
[[ "$MODE" == check || "$MODE" == promote || "$MODE" == rollback ]] || usage
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Reuse the existing receipt, source-commit, and digest validator without changing its draft-only stage mode.
bash "$ROOT/scripts/deploy_bookworks_original_html.sh" --release "$RELEASE" --mode check
readarray -t FIELDS < <(python3 - "$RELEASE" <<'PY'
import json,pathlib,sys
r=pathlib.Path(sys.argv[1]); p=json.loads((r/'wordpress.json').read_text())
print(p['publication_id']+':'+p['profile'])
print(p['slug'])
print(p['source_commit'])
PY
)
KEY="${FIELDS[0]}"; SLUG="${FIELDS[1]}"; REV="${FIELDS[2]}"
HTML="$RELEASE/original-html/$SLUG.html"
[[ -f "$HTML" ]] || { echo "Approved HTML filename differs from slug; inspect release" >&2; exit 1; }
HASH="$(sha256sum "$HTML" | awk '{print $1}')"
CONTAINER=docker-rootedpsyche-wordpress-1
REMOTE="/var/www/html/bookworks/$SLUG.html"
BACKUP_DIR="/var/www/html/bookworks/.approved-history/$SLUG"
PHP=/tmp/promote_bookworks_original_html.php
sudo docker cp "$ROOT/scripts/promote_bookworks_original_html.php" "$CONTAINER:$PHP"
sudo docker exec "$CONTAINER" php "$PHP" "$KEY" "$SLUG" "$HASH" check
if [[ "$MODE" == check ]]; then echo "Promotion preflight complete (read-only WordPress/HTML state)."; exit 0; fi
if [[ "$MODE" == rollback ]]; then
  echo "Rollback is intentionally manual until a recorded, verified prior revision can be selected." >&2
  exit 2
fi
# Adopt only an exact published shortcode page, never create/recreate it.
sudo docker exec "$CONTAINER" php "$PHP" "$KEY" "$SLUG" "$HASH" adopt
sudo docker exec "$CONTAINER" mkdir -p "$BACKUP_DIR"
# Preserve prior bytes under a content-addressed filename before any replacement.
if sudo docker exec "$CONTAINER" test -f "$REMOTE"; then
 OLD="$(sudo docker exec "$CONTAINER" sha256sum "$REMOTE" | awk '{print $1}')"
 sudo docker exec "$CONTAINER" cp -n "$REMOTE" "$BACKUP_DIR/$OLD.html"
 [[ "$(sudo docker exec "$CONTAINER" sha256sum "$BACKUP_DIR/$OLD.html" | awk '{print $1}')" == "$OLD" ]] || { echo "Backup hash mismatch" >&2; exit 1; }
fi
TMP="/var/www/html/bookworks/.$SLUG.$HASH.tmp"
sudo docker cp "$HTML" "$CONTAINER:$TMP"
[[ "$(sudo docker exec "$CONTAINER" sha256sum "$TMP" | awk '{print $1}')" == "$HASH" ]] || { echo "Uploaded HTML hash mismatch" >&2; exit 1; }
sudo docker exec "$CONTAINER" mv -f "$TMP" "$REMOTE"
sudo docker exec "$CONTAINER" php "$PHP" "$KEY" "$SLUG" "$HASH" record
echo "Promoted $KEY at existing WordPress page; revision $REV, sha256 $HASH"
