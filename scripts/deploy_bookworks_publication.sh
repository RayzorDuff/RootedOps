#!/usr/bin/env bash
# BookWorks -> WordPress draft deployment, phase 1.
# Never publishes, changes menus, or replaces a published page.
set -Eeuo pipefail
usage() {
  cat >&2 <<'HELP'
Usage: bash scripts/deploy_bookworks_publication.sh --payload FILE [--mode check|stage] [--expected-key PUBLICATION:PROFILE]
  check  Validate locally, install nothing, and ask WordPress for a read-only plan (default).
  stage  Validate, install the managed presentation, and create/update a DRAFT only.
         A published page may be checked but never changed by this command.
HELP
  exit 2
}
PAYLOAD=""
MODE=check
EXPECTED_KEY=""
while (($#)); do
  case "$1" in
    --payload) (($# >= 2)) || usage; PAYLOAD="$2"; shift 2 ;;
    --mode) (($# >= 2)) || usage; MODE="$2"; shift 2 ;;
    --expected-key) (($# >= 2)) || usage; EXPECTED_KEY="$2"; shift 2 ;;
    *) usage ;;
  esac
done
[[ -n "$PAYLOAD" && -f "$PAYLOAD" ]] || usage
[[ "$MODE" == check || "$MODE" == stage ]] || usage
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Validate before touching WordPress or installing presentation assets.
python3 - "$PAYLOAD" "$EXPECTED_KEY" <<'PY'
import hashlib, json, re, sys
from pathlib import Path
path, expected = sys.argv[1:]
data = json.loads(Path(path).read_text(encoding="utf-8"))
if not isinstance(data, dict):
    raise SystemExit("Payload must be a JSON object")
required = ("publication_id", "profile", "source_commit", "title", "slug", "html", "html_sha256")
for name in required:
    if not isinstance(data.get(name), str) or not data[name].strip():
        raise SystemExit(f"Missing/invalid payload field: {name}")
if data.get("schema_version") != 1:
    raise SystemExit("Only BookWorks WordPress schema version 1 is supported")
if data.get("layout") not in ("fundraising-landing", "public-edition"):
    raise SystemExit("Unsupported WordPress layout")
if data.get("media") != []:
    raise SystemExit("Media manifest is not yet supported; refusing incomplete deployment")
if not re.fullmatch(r"[a-f0-9]{40}", data["source_commit"]):
    raise SystemExit("Invalid source commit")
if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", data["publication_id"]):
    raise SystemExit("Invalid publication ID")
if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", data["profile"]):
    raise SystemExit("Invalid profile")
if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", data["slug"]):
    raise SystemExit("Invalid slug")
digest = hashlib.sha256(data["html"].encode("utf-8")).hexdigest()
if digest != data["html_sha256"]:
    raise SystemExit("HTML SHA-256 mismatch")
key = data["publication_id"] + ":" + data["profile"]
if expected and expected != key:
    raise SystemExit(f"Expected key {expected!r}, package contains {key!r}")
print(f"Validated BookWorks package: {key} at {data['source_commit'][:12]} (sha256 {digest[:12]})")
PY
if [[ "$MODE" == stage ]]; then
  LAYOUT="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["layout"])' "$PAYLOAD")"
  if [[ "$LAYOUT" == fundraising-landing ]]; then
    bash "$ROOT/scripts/install_bookworks_fundraising_styles.sh"
  fi
fi
# The existing importer performs WordPress-side uniqueness, slug ownership,
# stored-content checksum, and published-page checks.
if [[ "$MODE" == check ]]; then
  bash "$ROOT/scripts/import_bookworks_publication.sh" "$PAYLOAD" dry-run
else
  bash "$ROOT/scripts/import_bookworks_publication.sh" "$PAYLOAD" draft
  bash "$ROOT/scripts/import_bookworks_publication.sh" "$PAYLOAD" dry-run
fi
