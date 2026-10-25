#!/usr/bin/env bash
# Controlled in-place deployment of approved BookWorks HTML; no page recreation.
set -Eeuo pipefail
usage() {
 echo "Usage: bash scripts/promote_bookworks_original_html.sh --release ABSOLUTE_DIR --mode check|promote|rollback [--to-sha SHA256]" >&2
 exit 2
}
RELEASE="" MODE="" TO_SHA=""
while (($#)); do
 case "$1" in
  --release) RELEASE="${2:-}"; shift 2;;
  --mode) MODE="${2:-}"; shift 2;;
  --to-sha) TO_SHA="${2:-}"; shift 2;;
  *) usage;;
 esac
done
[[ -n "$RELEASE" && -d "$RELEASE" && "$RELEASE" = /* ]] || usage
[[ "$MODE" == check || "$MODE" == promote || "$MODE" == rollback ]] || usage
if [[ "$MODE" == rollback ]]; then
 [[ "$TO_SHA" =~ ^[a-f0-9]{64}$ ]] || usage
else
 [[ -z "$TO_SHA" ]] || usage
fi
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RELEASE="$(realpath "$RELEASE")"
# Validation is shared with draft-stage, but stage itself is never called.
bash "$ROOT/scripts/deploy_bookworks_original_html.sh" --release "$RELEASE" --mode check
readarray -t FIELDS < <(python3 - "$RELEASE" <<'PY'
import json,pathlib,sys
r=pathlib.Path(sys.argv[1]); p=json.loads((r/'wordpress.json').read_text())
print(p['publication_id']+':'+p['profile'])
print(p['slug'])
print(p['source_commit'])
PY
)
[[ "${#FIELDS[@]}" == 3 ]] || { echo "Invalid release payload" >&2; exit 1; }
KEY="${FIELDS[0]}"; SLUG="${FIELDS[1]}"; REV="${FIELDS[2]}"
HTML="$RELEASE/original-html/$SLUG.html"
[[ -f "$HTML" && ! -L "$HTML" ]] || { echo "Expected approved slug HTML file" >&2; exit 1; }
HASH="$(sha256sum "$HTML" | awk '{print $1}')"
CONTAINER="${BOOKWORKS_WORDPRESS_CONTAINER:-docker-rootedpsyche-wordpress-1}"
REMOTE="/var/www/html/bookworks/$SLUG.html"
BACKUP_DIR="/var/www/html/bookworks/.approved-history/$SLUG"
PHP=/tmp/promote_bookworks_original_html.php
# A read-only check may copy the helper but does not change the WordPress DB or publication HTML.
sudo docker cp "$ROOT/scripts/promote_bookworks_original_html.php" "$CONTAINER:$PHP"
sudo docker exec "$CONTAINER" php "$PHP" "$KEY" "$SLUG" "$HASH" check
if [[ "$MODE" == check ]]; then
 echo "Preflight complete: approved $KEY at revision $REV. No page or HTML modified."
 exit 0
fi
sudo docker exec "$CONTAINER" mkdir -p "$BACKUP_DIR"
# Never replace an existing live document without a verified, immutable backup.
if sudo docker exec "$CONTAINER" test -f "$REMOTE"; then
 OLD="$(sudo docker exec "$CONTAINER" sha256sum "$REMOTE" | awk '{print $1}')"
 [[ "$OLD" =~ ^[a-f0-9]{64}$ ]] || exit 1
 sudo docker exec "$CONTAINER" cp -n "$REMOTE" "$BACKUP_DIR/$OLD.html"
 [[ "$(sudo docker exec "$CONTAINER" sha256sum "$BACKUP_DIR/$OLD.html" | awk '{print $1}')" == "$OLD" ]] || { echo "Backup checksum mismatch" >&2; exit 1; }
else
 [[ "$MODE" != rollback ]] || { echo "Cannot roll back missing live HTML" >&2; exit 1; }
 OLD=""
fi
if [[ "$MODE" == rollback ]]; then
 SOURCE="$BACKUP_DIR/$TO_SHA.html"
 sudo docker exec "$CONTAINER" test -f "$SOURCE" || { echo "No archived HTML with requested checksum" >&2; exit 1; }
 [[ "$(sudo docker exec "$CONTAINER" sha256sum "$SOURCE" | awk '{print $1}')" == "$TO_SHA" ]] || { echo "Archived HTML checksum mismatch" >&2; exit 1; }
 TARGET_HASH="$TO_SHA"
 TMP="/var/www/html/bookworks/.$SLUG.$TO_SHA.rollback.tmp"
 sudo docker exec "$CONTAINER" cp "$SOURCE" "$TMP"
else
 TARGET_HASH="$HASH"
 TMP="/var/www/html/bookworks/.$SLUG.$HASH.promote.tmp"
 sudo docker cp "$HTML" "$CONTAINER:$TMP"
fi
[[ "$(sudo docker exec "$CONTAINER" sha256sum "$TMP" | awk '{print $1}')" == "$TARGET_HASH" ]] || { echo "Temporary HTML checksum mismatch" >&2; exit 1; }
# Adopt existing page 41 (or equivalent) only after validating the exact shortcode.
sudo docker exec "$CONTAINER" php "$PHP" "$KEY" "$SLUG" "$TARGET_HASH" adopt
# mv is atomic within the WordPress container's filesystem.
sudo docker exec "$CONTAINER" mv -f "$TMP" "$REMOTE"
# If this fails, old content remains in the verified content-addressed history.
sudo docker exec "$CONTAINER" php "$PHP" "$KEY" "$SLUG" "$TARGET_HASH" record
echo "$MODE succeeded for $KEY at existing WordPress page. source=$REV sha256=$TARGET_HASH previous=${OLD:-none}"
