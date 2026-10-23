#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ $# -ne 2 ]]; then echo "Usage: sudo bash scripts/install_rootedpsyche_branding.sh /path/to/logo.png /path/to/tree-icon.png" >&2; exit 2; fi
container="docker-rootedpsyche-wordpress-1"
docker cp "$1" "$container:/tmp/rootedpsyche-brand-logo.png"
docker cp "$2" "$container:/tmp/rootedpsyche-brand-icon.png"
docker exec "$container" mkdir -p /var/www/html/wp-content/mu-plugins
docker cp wordpress/mu-plugins/rootedpsyche-branding.php "$container:/var/www/html/wp-content/mu-plugins/rootedpsyche-branding.php"
docker cp scripts/install_rootedpsyche_branding.php "$container:/tmp/install_rootedpsyche_branding.php"
docker exec -u www-data "$container" php /tmp/install_rootedpsyche_branding.php
