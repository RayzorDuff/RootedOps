#!/usr/bin/env bash
set -Eeuo pipefail
# Candidate image only: never change live image tags, containers or volumes.
usage() {
  echo 'Usage: scripts/erpnext_image_candidate.sh [--build] [--tag rootedops-erpnext:review-NAME]'
  echo 'Default verifies an existing candidate. --build explicitly creates a new candidate.'
}
build=false
tag=""
while (($#)); do
  case "$1" in
    --build) build=true; shift ;;
    --tag) (($# >= 2)) || { usage >&2; exit 2; }; tag="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"
[[ -f .env && -f docker/docker-compose.yml ]] || { echo "Missing deployment configuration" >&2; exit 1; }
commit="$(git rev-parse --short=12 HEAD)"
tag="${tag:-rootedops-erpnext:review-$commit}"
[[ "$tag" =~ ^rootedops-erpnext:review-[a-zA-Z0-9_.-]+$ ]] ||
  { echo "Refusing non-candidate image tag: $tag" >&2; exit 2; }
compose=(sudo docker compose --env-file ./.env -f docker/docker-compose.yml)
if "$build"; then
  mapfile -t args < <("${compose[@]}" config --format json |
    python3 -c '
import json,sys
cfg=json.load(sys.stdin)
values=cfg["services"]["erpnext-backend"]["build"]["args"]
for key in ("ERPNEXT_IMAGE_TAG","ERPNEXT_HRMS_BRANCH","ERPNEXT_ESS_BRANCH"):
    val=values.get(key)
    if not isinstance(val,str) or not val or "\n" in val:
        raise SystemExit("Missing or invalid image build arg: "+key)
    print(val)
')
  (("${#args[@]}" == 3)) || { echo "Cannot resolve image build arguments" >&2; exit 1; }
  echo "Building candidate $tag from $commit; live Compose tag remains untouched."
  sudo docker build --pull=false \
    -f docker/erpnext-custom.Dockerfile \
    --build-arg "ERPNEXT_IMAGE_TAG=${args[0]}" \
    --build-arg "ERPNEXT_HRMS_BRANCH=${args[1]}" \
    --build-arg "ERPNEXT_ESS_BRANCH=${args[2]}" \
    --tag "$tag" .
fi
sudo docker image inspect "$tag" >/dev/null ||
  { echo "Candidate image missing; rerun with --build" >&2; exit 1; }
echo "Verifying $tag with no mounted volumes and no network"
sudo docker run --rm --network none \
  --entrypoint /home/frappe/frappe-bench/env/bin/python "$tag" -c '
from pathlib import Path
import importlib
for name in ("rootedops_payroll","rootedops_commerce"):
    mod=importlib.import_module(name)
    path=Path(mod.__file__).resolve()
    root=Path("/home/frappe/frappe-bench/apps") / name
    if not path.is_relative_to(root):
        raise SystemExit("Unexpected app import path: "+str(path))
    print(name,getattr(mod,"__version__","unversioned"),path)
'
echo "Candidate imports passed; no production container or volume changes."
sudo docker image inspect "$tag" --format 'Image ID: {{.Id}}'
