#!/usr/bin/env bash
# Consume an approved BookWorksArtifacts WordPress release. Never publish.
set -Eeuo pipefail
usage() { echo "Usage: bash scripts/deploy_bookworks_artifact.sh --release DIRECTORY [--mode check|stage]" >&2; exit 2; }
RELEASE="" MODE=check
while (($#)); do
  case "$1" in
    --release) (($# >= 2)) || usage; RELEASE="$2"; shift 2 ;;
    --mode) (($# >= 2)) || usage; MODE="$2"; shift 2 ;;
    *) usage ;;
  esac
done
[[ "$MODE" == check || "$MODE" == stage ]] || usage
[[ -n "$RELEASE" && -d "$RELEASE" ]] || usage
RELEASE="$(realpath "$RELEASE")"
# Refuse release files without a matching approval receipt and checksums.
python3 - "$RELEASE" <<'PY'
import hashlib, json, pathlib, re, sys
root = pathlib.Path(sys.argv[1])
receipt = json.loads((root / "approval.json").read_text())
payload = json.loads((root / "wordpress.json").read_text())
manifest = json.loads((root / "media/manifest.json").read_text())
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
assert receipt["approval"] == "approved-for-wordpress-draft"
assert receipt["schema_version"] == 1
assert re.fullmatch(r"[0-9a-f]{40}", receipt["source_commit"])
assert receipt["source_commit"] == payload["source_commit"]
assert receipt["publication_key"] == payload["publication_id"] + ":" + payload["profile"]
assert receipt["publication_key"] == manifest["publication_key"]
assert receipt["wordpress_slug"] == payload["slug"]
assert receipt["payload_sha256"] == digest(root / "wordpress.json")
assert receipt["media_manifest_sha256"] == digest(root / "media/manifest.json")
assert len(manifest["assets"]) == 6
assert {a["role"] for a in manifest["assets"]} == {"cover", *(f"chapter-{i:02d}" for i in range(1, 6))}
for asset in manifest["assets"]:
    name = asset["filename"]
    assert pathlib.Path(name).name == name and ".." not in name
    assert digest(root / "media/assets" / name) == asset["sha256"]
print("Verified approved WordPress release:", receipt["publication_key"])
PY
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KEY="$(python3 - "$RELEASE/approval.json" <<'PY'
import json,sys
print(json.load(open(sys.argv[1]))["publication_key"])
PY
)"
bash "$ROOT/scripts/deploy_bookworks_publication.sh" --payload "$RELEASE/wordpress.json" --expected-key "$KEY" --mode "$MODE"
if [[ "$MODE" == stage ]]; then
  bash "$ROOT/scripts/sync_bookworks_media.sh" "$RELEASE/media/manifest.json" "$RELEASE/media/assets" check
  bash "$ROOT/scripts/sync_bookworks_media.sh" "$RELEASE/media/manifest.json" "$RELEASE/media/assets" stage
  bash "$ROOT/scripts/deploy_bookworks_publication.sh" --payload "$RELEASE/wordpress.json" --expected-key "$KEY" --mode stage
fi
