#!/usr/bin/env bash
# Install the original, checksum-approved BookWorks HTML without reformatting.
set -Eeuo pipefail
usage(){ echo "Usage: bash scripts/deploy_bookworks_original_html.sh --release DIR --html FILE [--mode check|stage]" >&2; exit 2; }
RELEASE="" HTML="" MODE=check
while (($#)); do
 case "$1" in
 --release) RELEASE="${2:-}"; shift 2;;
 --html) HTML="${2:-}"; shift 2;;
 --mode) MODE="${2:-}"; shift 2;;
 *) usage;;
 esac
done
[[ "$MODE" == check || "$MODE" == stage ]] || usage
[[ -d "$RELEASE" && -f "$HTML" ]] || usage
RELEASE="$(realpath "$RELEASE")"; HTML="$(realpath "$HTML")"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# The approved release must explicitly bind this original HTML digest to its receipt.
readarray -t DETAILS < <(python3 - "$RELEASE" "$HTML" <<'PY'
import hashlib,json,pathlib,re,sys
root=pathlib.Path(sys.argv[1]); html=pathlib.Path(sys.argv[2])
receipt=json.loads((root/'approval.json').read_text())
payload=json.loads((root/'wordpress.json').read_text())
if receipt.get('approval')!='approved-for-wordpress-draft' or receipt.get('schema_version')!=1: raise SystemExit('Unapproved release')
if receipt.get('payload_sha256')!=hashlib.sha256((root/'wordpress.json').read_bytes()).hexdigest(): raise SystemExit('Payload checksum mismatch')
if receipt.get('publication_key')!=payload.get('publication_id')+':'+payload.get('profile'): raise SystemExit('Key mismatch')
if receipt.get('source_commit')!=payload.get('source_commit'): raise SystemExit('Source mismatch')
slug=payload.get('slug','')
if not re.fullmatch('[a-z0-9][a-z0-9-]{0,180}',slug): raise SystemExit('Invalid slug')
# No reliance on manually selected HTML: receipt must attest to these exact bytes.
expected=receipt.get('original_html_sha256')
actual=hashlib.sha256(html.read_bytes()).hexdigest()
if not isinstance(expected,str) or not re.fullmatch('[a-f0-9]{64}',expected) or expected!=actual: raise SystemExit('Original HTML is not approved by receipt')
if html.is_symlink() or html.suffix!='.html': raise SystemExit('Invalid HTML file')
print(receipt['publication_key']);print(slug);print(actual)
PY
)
[[ "${#DETAILS[@]}" == 3 ]] || { echo "Release validation failed" >&2; exit 1; }
KEY="${DETAILS[0]}"; SLUG="${DETAILS[1]}"; HASH="${DETAILS[2]}"
CONTAINER="docker-rootedpsyche-wordpress-1"
if [[ "$MODE" == check ]]; then
 echo "Approved original HTML: $KEY -> $SLUG.html ($HASH)"
 echo "Read-only check complete; stage installs the plugin and HTML, then creates an unpublished page."
 exit 0
fi
# Stage to a temporary file; checksum verified before final rename.
sudo docker exec "$CONTAINER" mkdir -p /var/www/html/bookworks /var/www/html/wp-content/plugins/bookworks-original-html
sudo docker cp "$ROOT/wordpress/plugins/bookworks-original-html/bookworks-original-html.php" "$CONTAINER:/var/www/html/wp-content/plugins/bookworks-original-html/bookworks-original-html.php"
sudo docker cp "$HTML" "$CONTAINER:/var/www/html/bookworks/.$SLUG.html.tmp"
REMOTE_HASH="$(sudo docker exec "$CONTAINER" sha256sum "/var/www/html/bookworks/.$SLUG.html.tmp" | awk '{print $1}')"
[[ "$REMOTE_HASH" == "$HASH" ]] || { echo "Container checksum mismatch" >&2; exit 1; }
sudo docker exec "$CONTAINER" mv "/var/www/html/bookworks/.$SLUG.html.tmp" "/var/www/html/bookworks/$SLUG.html"
echo "Installed original HTML. Activate 'BookWorks Original HTML Renderer' in WordPress, then run:"
echo "sudo docker cp scripts/stage_bookworks_original_html.php $CONTAINER:/tmp/stage_bookworks_original_html.php"
echo "sudo docker exec $CONTAINER php /tmp/stage_bookworks_original_html.php '$KEY' '$SLUG' check"
echo "sudo docker exec $CONTAINER php /tmp/stage_bookworks_original_html.php '$KEY' '$SLUG' stage"
