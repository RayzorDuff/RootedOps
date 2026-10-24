#!/usr/bin/env bash
# Install the original, checksum-approved BookWorks HTML without reformatting.
set -Eeuo pipefail
usage(){ echo "Usage: bash scripts/deploy_bookworks_original_html.sh --release DIR [--html FILE] [--mode check|stage]" >&2; exit 2; }
RELEASE="" HTML="" MODE=check
ARTIFACT_ROOT="${BOOKWORKS_ARTIFACT_ROOT:-/mnt/GoogleDrive-ray@edanks.com/BookWorksArtifacts}"
while (($#)); do
 case "$1" in
 --release) RELEASE="${2:-}"; shift 2;;
 --html) HTML="${2:-}"; shift 2;;
 --mode) MODE="${2:-}"; shift 2;;
 --artifact-root) ARTIFACT_ROOT="${2:-}"; shift 2;;
 *) usage;;
 esac
done
[[ "$MODE" == check || "$MODE" == stage ]] || usage
if [[ -z "$RELEASE" ]]; then
  RELEASE="$ARTIFACT_ROOT/rooted-psyche-spiritual-foundations/wordpress-original-html/public-introduction"
  [[ -d "$RELEASE" ]] || { echo "Artifact release directory missing: $RELEASE" >&2; exit 1; }
  readarray -t RELEASES < <(find "$RELEASE" -mindepth 1 -maxdepth 1 -type d ! -name ".*" | sort)
  [[ "${#RELEASES[@]}" == 1 ]] || { echo "Specify --release explicitly when multiple releases exist" >&2; exit 1; }
  RELEASE="${RELEASES[0]}"
fi
[[ -d "$RELEASE" ]] || usage
RELEASE="$(realpath "$RELEASE")"
if [[ -z "$HTML" ]]; then
  readarray -t MATCHES < <(find "$RELEASE/original-html" -maxdepth 1 -type f -name "*.html" 2>/dev/null)
  [[ "${#MATCHES[@]}" == 1 ]] || { echo "Expected one packaged original HTML file" >&2; exit 1; }
  HTML="${MATCHES[0]}"
fi
HTML="$(realpath "$HTML")"
[[ "$HTML" == "$RELEASE"/original-html/* ]] || { echo "HTML must come from approved release" >&2; exit 1; }
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
sidecar=root/'original-html-approval.json'
if not sidecar.is_file(): raise SystemExit('Missing separately reviewed original-html-approval.json')
approval=json.loads(sidecar.read_text())
if approval.get('approval')!='approved-original-html-for-wordpress-draft': raise SystemExit('Original HTML not approved')
if 'approval_receipt_sha256' in approval and approval['approval_receipt_sha256']!=hashlib.sha256((root/'approval.json').read_bytes()).hexdigest(): raise SystemExit('Original approval receipt changed')
if approval.get('publication_key')!=receipt.get('publication_key') or approval.get('source_commit')!=receipt.get('source_commit'): raise SystemExit('Original HTML approval provenance mismatch')
if approval.get('original_html_filename')!=html.name: raise SystemExit('Original HTML filename mismatch')
expected=approval.get('original_html_sha256')
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
# Never replace the live static document while a managed page is published.
# A draft can be refreshed; publishing requires a separate explicit action.
sudo docker exec -i "$CONTAINER" php /dev/stdin "$KEY" "$SLUG" <<'PHP'
<?php
require '/var/www/html/wp-load.php';
$key = $argv[1]; $slug = $argv[2];
$matches = get_posts(['post_type'=>'page','post_status'=>'any','numberposts'=>-1,
  'meta_key'=>'_bookworks_original_key','meta_value'=>$key]);
if (count($matches) > 1) { fwrite(STDERR, "Multiple managed pages; refusing update\\n"); exit(1); }
if ($matches && $matches[0]->post_status !== 'draft') {
  fwrite(STDERR, "Managed page is not a draft; refusing live HTML replacement\\n"); exit(1);
}
$owner = get_page_by_path($slug, OBJECT, 'page');
if ($owner && (!$matches || $owner->ID !== $matches[0]->ID)) {
  fwrite(STDERR, "Slug belongs to another WordPress page\\n"); exit(1);
}
PHP
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
