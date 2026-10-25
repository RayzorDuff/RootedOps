#!/usr/bin/env bash
# Explicit, receipt-verified migration of an existing iframe draft to WordPress-native content.
set -Eeuo pipefail
usage(){ echo "Usage: bash scripts/convert_bookworks_original_draft.sh --release DIR --page-id ID --mode check|convert" >&2; exit 2; }
RELEASE="" PAGE_ID="" MODE=check
while (($#)); do
 case "$1" in
  --release) RELEASE="${2:-}"; shift 2;;
  --page-id) PAGE_ID="${2:-}"; shift 2;;
  --mode) MODE="${2:-}"; shift 2;;
  *) usage;;
 esac
done
[[ "$MODE" == check || "$MODE" == convert ]] || usage
[[ "$PAGE_ID" =~ ^[1-9][0-9]*$ && -d "$RELEASE" ]] || usage
RELEASE="$(realpath "$RELEASE")"
python3 - "$RELEASE" <<'PY'
import hashlib,json,pathlib,sys,re
root=pathlib.Path(sys.argv[1])
receipt=json.loads((root/'approval.json').read_text())
payload=json.loads((root/'wordpress.json').read_text())
manifest=json.loads((root/'media/manifest.json').read_text())
digest=lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
assert receipt['approval']=='approved-for-wordpress-draft'
assert receipt['schema_version']==1
assert receipt['publication_key']==payload['publication_id']+':'+payload['profile']
assert receipt['source_commit']==payload['source_commit']
assert receipt['wordpress_slug']==payload['slug']
assert receipt['payload_sha256']==digest(root/'wordpress.json')
assert receipt['media_manifest_sha256']==digest(root/'media/manifest.json')
assert manifest['publication_key']==receipt['publication_key']
assert payload['layout']=='fundraising-landing'
assert len(manifest['assets'])>=1
for asset in manifest['assets']:
    name=asset['filename']
    assert re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,160}',name) and '..' not in name
    assert digest(root/'media/assets'/name)==asset['sha256']
print('Verified approved native fundraising release:',receipt['publication_key'])
PY
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONTAINER="${BOOKWORKS_WORDPRESS_CONTAINER:-docker-rootedpsyche-wordpress-1}"
REMOTE="/tmp/bookworks-native-conversion-$$"
trap 'sudo docker exec "$CONTAINER" rm -f "$REMOTE.json" "$REMOTE.php" >/dev/null 2>&1 || true' EXIT
sudo docker cp "$RELEASE/wordpress.json" "$CONTAINER:$REMOTE.json"
sudo docker cp "$ROOT/scripts/convert_bookworks_original_draft.php" "$CONTAINER:$REMOTE.php"
sudo docker exec "$CONTAINER" php "$REMOTE.php" "$REMOTE.json" "$PAGE_ID" "$MODE"
