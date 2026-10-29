#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
container="docker-rootedpsyche-wordpress-1"
source_md="grav.mysite/user/pages/01.home/default.md"
source_qr="grav.mysite/user/pages/01.home/qr.png"
[[ -f "$source_md" && -f "$source_qr" ]] || { echo "Grav source files missing" >&2; exit 1; }
docker inspect -f '{{.State.Running}}' "$container" | grep -qx true
docker cp "$source_md" "$container:/tmp/rootedpsyche-grav-home.md"
docker cp "$source_qr" "$container:/tmp/rootedpsyche-qr.png"
docker exec "$container" mkdir -p /var/www/html/wp-content/mu-plugins
docker cp wordpress/mu-plugins/rootedpsyche-givebutter.php "$container:/var/www/html/wp-content/mu-plugins/rootedpsyche-givebutter.php"
docker cp scripts/import_rootedpsyche_home.php "$container:/tmp/import_rootedpsyche_home.php"
# Optional verified Givebutter campaign URL; do not infer it from the widget ID.
docker exec -u www-data -e ROOTEDPSYCHE_GIVEBUTTER_URL="${ROOTEDPSYCHE_GIVEBUTTER_URL:-}" "$container" php /tmp/import_rootedpsyche_home.php
