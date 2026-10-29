#!/usr/bin/env bash
# Synchronize approved BookWorks media into an existing managed WordPress draft.
set -Eeuo pipefail
if [[ $# != 3 || ( "$3" != check && "$3" != stage ) ]]; then
  echo "Usage: bash scripts/sync_bookworks_media.sh MANIFEST.json ASSET_DIRECTORY check|stage" >&2
  exit 2
fi
MANIFEST="$(realpath "$1")"
ASSETS="$(realpath "$2")"
MODE="$3"
[[ -f "$MANIFEST" && -d "$ASSETS" ]] || { echo "Manifest or assets missing" >&2; exit 2; }
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONTAINER="docker-rootedpsyche-wordpress-1"
REMOTE="/tmp/bookworks-media-$$"
cleanup() { sudo docker exec "$CONTAINER" rm -rf "$REMOTE" >/dev/null 2>&1 || true; }
trap cleanup EXIT
# No directory traversal or symlinks; only approved file names and hashes.
python3 - "$MANIFEST" "$ASSETS" <<'PY'
import hashlib, json, pathlib, re, sys
manifest = json.loads(pathlib.Path(sys.argv[1]).read_text())
assert manifest.get("schema_version") == 1
assets = manifest.get("assets")
assert isinstance(assets, list) and 0 < len(assets) <= 30
roles = set()
for a in assets:
    role, name, sha = a["role"], a["filename"], a["sha256"]
    assert re.fullmatch(r"[a-z][a-z0-9-]{0,50}", role) and role not in roles
    roles.add(role)
    assert re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,160}", name) and ".." not in name
    path = pathlib.Path(sys.argv[2]) / name
    assert path.is_file() and not path.is_symlink()
    assert hashlib.sha256(path.read_bytes()).hexdigest() == sha
print(f"Verified {len(assets)} media assets")
PY
sudo docker exec "$CONTAINER" mkdir -p "$REMOTE/assets"
sudo docker cp "$MANIFEST" "$CONTAINER:$REMOTE/manifest.json"
# Transfer only the explicitly validated manifest entries, not the entire directory.
while IFS= read -r name; do
  sudo docker cp "$ASSETS/$name" "$CONTAINER:$REMOTE/assets/$name"
done < <(python3 - "$MANIFEST" <<'PY'
import json, sys
for asset in json.load(open(sys.argv[1]))["assets"]:
    print(asset["filename"])
PY
)
sudo docker cp "$ROOT/scripts/sync_bookworks_media.php" "$CONTAINER:$REMOTE/sync.php"
sudo docker exec "$CONTAINER" php "$REMOTE/sync.php" "$REMOTE/manifest.json" "$REMOTE/assets" "$MODE"
