#!/usr/bin/env bash
set -Eeuo pipefail
# Stop only two shared test2 Docker projects; keep all volumes, containers,
# databases, image tags and evidence. No Compose down/prune/remove commands.
usage() {
  echo 'Usage: scripts/stop_shared_test2.sh [--stop --confirm-shared-test2]'
  echo 'Read-only by default; use only on the separate shared test2 Linode.'
}
stop=false
confirmed=false
while (($#)); do
  case "$1" in
    --stop) stop=true; shift ;;
    --confirm-shared-test2) confirmed=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
done
if "$stop" && ! "$confirmed"; then
  echo 'ERROR: --stop requires --confirm-shared-test2' >&2
  exit 2
fi
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
marker="$ROOT/.test-deployment/TEST_ENVIRONMENT"
if [[ ! -f "$marker" || "$(cat "$marker")" != "rootedops-full-test" ]]; then
  echo 'ERROR: Missing shared test2 marker; refusing to touch containers' >&2
  exit 1
fi
projects=(rootedops-full-test dank-store-test)
for project in "${projects[@]}"; do
  mapfile -t containers < <(sudo docker ps -a --filter "label=com.docker.compose.project=$project" --format '{{.Names}}')
  if (("${#containers[@]}" == 0)); then
    echo "ERROR: expected test2 project absent: $project" >&2
    exit 1
  fi
  for container in "${containers[@]}"; do
    owner="$(sudo docker inspect "$container" --format '{{index .Config.Labels "com.docker.compose.project"}}')"
    [[ "$owner" == "$project" ]] || { echo "ERROR: unexpected ownership: $container" >&2; exit 1; }
  done
  echo "Project $project: ${#containers[@]} containers"
  sudo docker ps -a --filter "label=com.docker.compose.project=$project" --format '  {{.Names}} {{.Status}}'
done
if ! "$stop"; then
  echo 'READ ONLY. Preserve private receipts/backup and coordinate with other test2 users first.'
  exit 0
fi
for project in "${projects[@]}"; do
  mapfile -t running < <(sudo docker ps --filter "label=com.docker.compose.project=$project" --format '{{.Names}}')
  if (("${#running[@]}" > 0)); then sudo docker stop "${running[@]}"; fi
done
for project in "${projects[@]}"; do
  [[ -z "$(sudo docker ps -q --filter "label=com.docker.compose.project=$project")" ]] || {
    echo "ERROR: still-running test2 container in $project" >&2; exit 1;
  }
done
echo 'Test2 stopped; all containers/volumes/data retained.'
echo 'Does not change DNS, Nginx, Certbot, or unrelated Docker projects.'
