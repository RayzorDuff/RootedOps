#!/usr/bin/env bash
# Validate a BookWorks deployment ZIP and run a guarded WordPress check/stage.
set -Eeuo pipefail
if [[ $# -lt 2 || $# -gt 3 || ( "$2" != check && "$2" != stage ) ]]; then
  echo "Usage: bash scripts/deploy_bookworks_bundle.sh PACKAGE.zip check|stage [expected-publication-key]" >&2
  exit 2
fi
BUNDLE="$1"
MODE="$2"
EXPECTED="${3:-}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
python3 - "$BUNDLE" "$WORK" "$EXPECTED" <<'PY'
import hashlib, json, pathlib, re, sys, zipfile
bundle, root, expected = sys.argv[1:]
root = pathlib.Path(root)
with zipfile.ZipFile(bundle) as zf:
    entries = zf.infolist()
    names = [i.filename for i in entries]
    if len(names) != len(set(names)) or len(names) > 40:
        raise SystemExit("Duplicate or excessive ZIP entries")
    allowed = re.compile(r"(deployment\.json|publication\.json|media/manifest\.json|media/assets/[A-Za-z0-9][A-Za-z0-9._-]{0,160})")
    for info in entries:
        if not allowed.fullmatch(info.filename) or ".." in info.filename or info.is_dir():
            raise SystemExit("Unexpected ZIP entry")
        if (info.external_attr >> 16) & 0o170000 == 0o120000:
            raise SystemExit("Symlink ZIP entry rejected")
        if info.file_size > 25 * 1024 * 1024:
            raise SystemExit("Oversized ZIP entry")
    if "deployment.json" not in names or "publication.json" not in names:
        raise SystemExit("Missing deployment metadata")
    meta = json.loads(zf.read("deployment.json"))
    files = meta.get("files")
    if meta.get("schema_version") != 1 or not isinstance(files, dict) or set(files) != set(names) - {"deployment.json"}:
        raise SystemExit("Invalid file inventory")
    payload = json.loads(zf.read("publication.json"))
    key = payload["publication_id"] + ":" + payload["profile"]
    if meta.get("publication_key") != key or (expected and expected != key):
        raise SystemExit("Publication key mismatch")
    if ("media/manifest.json" in files) != any(n.startswith("media/assets/") for n in files):
        raise SystemExit("Incomplete media package")
    if "media/manifest.json" in files:
        manifest = json.loads(zf.read("media/manifest.json"))
        if manifest.get("publication_key") != key or manifest.get("schema_version") != 1:
            raise SystemExit("Media publication key mismatch")
        if {"media/assets/" + a["filename"] for a in manifest["assets"]} != {n for n in files if n.startswith("media/assets/")}:
            raise SystemExit("Media inventory mismatch")
    for name, digest in files.items():
        raw = zf.read(name)
        if not re.fullmatch(r"[0-9a-f]{64}", digest) or hashlib.sha256(raw).hexdigest() != digest:
            raise SystemExit("Package checksum mismatch: " + name)
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
print("Validated deployment bundle:", key)
PY
# Always check the content before staging. Stage only if it is safe to do so.
args=(--payload "$WORK/publication.json" --mode check)
if [[ -n "$EXPECTED" ]]; then args+=(--expected-key "$EXPECTED"); fi
bash "$ROOT/scripts/deploy_bookworks_publication.sh" "${args[@]}"
if [[ -f "$WORK/media/manifest.json" ]]; then
  # Read-only media check requires an existing managed page. For a brand-new
  # page, it becomes available after draft creation in stage mode.
  if [[ "$MODE" == check ]]; then
    bash "$ROOT/scripts/sync_bookworks_media.sh" "$WORK/media/manifest.json" "$WORK/media/assets" check
  fi
fi
if [[ "$MODE" == stage ]]; then
  args=(--payload "$WORK/publication.json" --mode stage)
  if [[ -n "$EXPECTED" ]]; then args+=(--expected-key "$EXPECTED"); fi
  bash "$ROOT/scripts/deploy_bookworks_publication.sh" "${args[@]}"
  if [[ -f "$WORK/media/manifest.json" ]]; then
    bash "$ROOT/scripts/sync_bookworks_media.sh" "$WORK/media/manifest.json" "$WORK/media/assets" stage
    bash "$ROOT/scripts/sync_bookworks_media.sh" "$WORK/media/manifest.json" "$WORK/media/assets" check
  fi
fi
