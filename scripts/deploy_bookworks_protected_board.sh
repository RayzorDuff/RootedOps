#!/usr/bin/env bash
# Deploy only the existing protected Rooted Psyche Board Readiness page.
set -Eeuo pipefail
usage(){ echo "Usage: $0 --release DIR --mode check|stage|promote|rollback [--to-sha SHA256]" >&2; exit 2; }
RELEASE="" MODE="" SHA="-"
while (($#)); do
  case "$1" in
    --release) RELEASE="${2:-}"; shift 2;;
    --mode) MODE="${2:-}"; shift 2;;
    --to-sha) SHA="${2:-}"; shift 2;;
    *) usage;;
  esac
done
[[ -d "$RELEASE" && "$MODE" =~ ^(check|stage|promote|rollback)$ ]] || usage
[[ "$MODE" == rollback && "$SHA" =~ ^[a-f0-9]{64}$ || "$MODE" != rollback && "$SHA" == "-" ]] || usage
RELEASE="$(realpath "$RELEASE")"
python3 - "$RELEASE" <<'PY'
import hashlib, json, pathlib, re, sys
root=pathlib.Path(sys.argv[1])
receipt=json.loads((root/'approval.json').read_text())
payload=json.loads((root/'wordpress.json').read_text())
media=json.loads((root/'media/manifest.json').read_text())
digest=lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
assert receipt['approval']=='approved-for-wordpress-draft'
assert receipt['publication_key']=='rooted-psyche-corporate-record-book:board-readiness'
assert payload['publication_id']== 'rooted-psyche-corporate-record-book'
assert payload['profile']=='board-readiness'
assert payload['slug']=='board-readiness'
assert receipt['source_commit']==payload['source_commit']
assert re.fullmatch('[a-f0-9]{40}',payload['source_commit'])
assert receipt['payload_sha256']==digest(root/'wordpress.json')
assert receipt['media_manifest_sha256']==digest(root/'media/manifest.json')
assert media['publication_key']==receipt['publication_key']
assert media['assets']==[]
assert payload['media']==[]
assert payload['html_sha256']==hashlib.sha256(payload['html'].encode()).hexdigest()
print("Verified protected Board Readiness release:",payload['source_commit'])
PY
CONTAINER="${BOOKWORKS_WORDPRESS_CONTAINER:-docker-rootedpsyche-wordpress-1}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# The host path is resolved from the live read-only Docker bind, avoiding a
# second, potentially divergent path setting in the deployment environment.
SUPPLEMENTS="$(sudo docker inspect "$CONTAINER" --format '{{range .Mounts}}{{if eq .Destination "/srv/rootedpsyche-board-supplements"}}{{.Source}}{{end}}{{end}}')"
[[ -n "$SUPPLEMENTS" && -d "$SUPPLEMENTS" ]] || {
  echo "Board supplements bind mount is missing from WordPress" >&2; exit 1;
}
[[ "$(findmnt -n -T "$SUPPLEMENTS" -o FSTYPE)" == fuse.rclone ]] || {
  echo "Board supplements path is not on the expected rclone filesystem" >&2; exit 1;
}
if [[ "$MODE" != rollback ]]; then
  python3 "$ROOT/scripts/board_working_documents_publish.py" \
    --release "$RELEASE" --supplements "$SUPPLEMENTS" --mode "$MODE"
fi
REMOTE="/tmp/rootedpsyche-board-release-$"
trap 'sudo docker exec "$CONTAINER" rm -f "$REMOTE.json" "$REMOTE.php" >/dev/null 2>&1 || true' EXIT
sudo docker cp "$RELEASE/wordpress.json" "$CONTAINER:$REMOTE.json"
sudo docker cp "$ROOT/scripts/board_protected_publish.php" "$CONTAINER:$REMOTE.php"
sudo docker exec "$CONTAINER" php "$REMOTE.php" "$REMOTE.json" "$MODE" "$SHA"
if [[ "$MODE" == promote ]]; then
  python3 "$ROOT/scripts/board_working_documents_publish.py" \
    --release "$RELEASE" --supplements "$SUPPLEMENTS" --mode promote
elif [[ "$MODE" == rollback ]]; then
  echo "Note: WordPress rollback does not change the separate Working Documents manifest." >&2
fi
