#!/usr/bin/env bash
# Install scoped BookWorks fundraising styles into the running WordPress container.
# Safe to repeat. Does not edit the theme, publish pages, or change site options.
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONTAINER="${WORDPRESS_CONTAINER:-docker-rootedpsyche-wordpress-1}"
TARGET="/var/www/html/wp-content/mu-plugins"
[[ -f "$ROOT/wordpress/bookworks-fundraising-loader.php" ]]
[[ -f "$ROOT/wordpress/bookworks-fundraising.css" ]]
sudo docker exec "$CONTAINER" mkdir -p "$TARGET"
sudo docker cp "$ROOT/wordpress/bookworks-fundraising-loader.php" "$CONTAINER:$TARGET/bookworks-fundraising-loader.php"
sudo docker cp "$ROOT/wordpress/bookworks-fundraising.css" "$CONTAINER:$TARGET/bookworks-fundraising.css"
sudo docker exec "$CONTAINER" php -l "$TARGET/bookworks-fundraising-loader.php"
echo "BookWorks fundraising styles installed; verify persistence and preview the managed draft."
