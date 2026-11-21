#!/usr/bin/env bash
# Disposable GitHub Actions fixture. Run only against synthetic CI services.
set -euo pipefail
[[ "${GITHUB_ACTIONS:-}" == true && "${COMMERCE_STAGING_ONLY:-}" == 1 ]]
fixture="$(mktemp -d)"
trap 'rm -rf "$fixture"' EXIT
curl -fsS --retry 2 https://wordpress.org/wordpress-7.1.4.tar.gz -o "$fixture/wp.tar.gz"
curl -fsS --retry 2 https://downloads.wordpress.org/plugin/woocommerce.11.2.1.zip -o "$fixture/woo.zip"
(
  cd "$fixture"
  sha256sum -c <<'SUM'
881e53a4681ff2cd911651b11cccdede5ae477ddf0765af5d6a1a8b219a1d835  wp.tar.gz
5317434cb381b5fdc7c1dd6ee258324f08c390976aaf8d1199f2a0e9a3ab8586  woo.zip
SUM
  tar -xzf wp.tar.gz
)
export COMMERCE_WP_ROOT="$fixture"
export COMMERCE_WP_CLI="$fixture/wp-cli"
cat > "$COMMERCE_WP_CLI" <<'WRAPPER'
#!/usr/bin/env bash
set -euo pipefail
exec docker run --rm --network host --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -e COMMERCE_NATIVE_WOO_FIXTURE=1 -v "$COMMERCE_WP_ROOT:/fixture" \
  -v "$GITHUB_WORKSPACE:$GITHUB_WORKSPACE:ro" --workdir /fixture/wordpress \
  --entrypoint wp wordpress:cli-php8.3 "$@"
WRAPPER
chmod +x "$COMMERCE_WP_CLI"
"$COMMERCE_WP_CLI" config create --dbname=woo_fixture --dbuser=woo_fixture \
  --dbpass=synthetic-ci-only --dbhost=127.0.0.1:3306 --skip-salts
"$COMMERCE_WP_CLI" config set WP_HTTP_BLOCK_EXTERNAL true --raw
mkdir -p "$fixture/wordpress/wp-content/mu-plugins"
printf '<?php add_filter("pre_wp_mail", "__return_true");\n' > \
  "$fixture/wordpress/wp-content/mu-plugins/ci-mail-sink.php"
"$COMMERCE_WP_CLI" core install --url=http://127.0.0.1:8100 --title='Native Woo fixture' \
  --admin_user=synthetic_admin --admin_password=synthetic-ci-only \
  --admin_email=wp@example.invalid --skip-email
"$COMMERCE_WP_CLI" option update home http://127.0.0.1:8100
"$COMMERCE_WP_CLI" option update siteurl http://127.0.0.1:8100
"$COMMERCE_WP_CLI" plugin install /fixture/woo.zip --activate
cp wordpress/dank-mu-plugins/rootedops-fulfillment.php "$fixture/wordpress/wp-content/mu-plugins/"
"$COMMERCE_WP_CLI" config set ROOTEDOPS_MP_WOO_ENABLED true --raw
"$COMMERCE_WP_CLI" config set ROOTEDOPS_MP_WOO_CUTOFF 0 --raw
"$COMMERCE_WP_CLI" eval-file "$GITHUB_WORKSPACE/scripts/commerce_woo_publication_ci.php"
"$COMMERCE_WP_CLI" eval-file "$GITHUB_WORKSPACE/scripts/commerce_wordpress_hostname_ci.php" seed
mkdir -m 700 "$fixture/hostname-private"
"$COMMERCE_WP_CLI" eval-file "$GITHUB_WORKSPACE/scripts/commerce_wordpress_hostname.php" preview
"$COMMERCE_WP_CLI" eval-file "$GITHUB_WORKSPACE/scripts/commerce_wordpress_hostname_ci.php" before
"$COMMERCE_WP_CLI" eval-file "$GITHUB_WORKSPACE/scripts/commerce_wordpress_hostname.php" apply /fixture/hostname-private/journal.json
"$COMMERCE_WP_CLI" eval-file "$GITHUB_WORKSPACE/scripts/commerce_wordpress_hostname_ci.php" after
"$COMMERCE_WP_CLI" eval-file "$GITHUB_WORKSPACE/scripts/commerce_wordpress_hostname.php" restore /fixture/hostname-private/journal.json
"$COMMERCE_WP_CLI" eval-file "$GITHUB_WORKSPACE/scripts/commerce_wordpress_hostname_ci.php" before
python integrations/commerce/test_inbox_postgres.py -v
