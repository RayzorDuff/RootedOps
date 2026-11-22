# Move the existing WordPress site to dankmushrooms.net

This procedure is independent of the unmerged Woo order stack in PRs #111–#124.
Use the existing production Linode, WordPress installation and ERP site. Ecwid stays live.
Do not deploy the stacked hostname runbook's NGINX templates over the existing net vhost.

Owner evidence on November 21: both HTTPS My Account routes return 200, NGINX validates,
home is https://shop-test.danks.store, and siteurl is http://shop-test.danks.store.
Both WordPress settings will become **https://dankmushrooms.net**.

## What stays the same

- Compose project `dank-store-test`, database, volumes, users, numeric Woo IDs and ERP links.
- Customer integration logical site `shop-test.danks.store`, including private inbox JSON keys.
- Existing customer webhook destination and secret, with direct routing on shop-test.
- Ecwid routing, inventory publisher, open orders and reservations.

The only ERP configuration additions are `commerce_customer_sync.woo_origin` and the explicit
same-installation approval. Never search-replace customer identities, history, webhook options,
order records, GUIDs or private configuration. Do not redirect the old vhost wholesale.
There is no requirement for an order listener on port 8102 for this customer-only hostname move.
Any already-installed Woo order adapters need their transport URL reviewed separately before use.

## 1. Merge the standalone change, back up, and deploy support

On the Linode, use main with no modified tracked files. These commands update code and restart
the existing ERP application services and Dank WordPress; they do not switch the WordPress URL.
Keep the shell open for later blocks. Do not paste backup files or credentials into chat.

```bash
set -euo pipefail
cd ~/RootedOps
test "$(git branch --show-current)" = main
test -z "$(git status --porcelain --untracked-files=no)"
git pull --ff-only origin main
sudo -v
umask 077
DOMAIN_BACKUP="$HOME/commerce-migration/hostname-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -m 700 -p "$DOMAIN_BACKUP"
dc=(sudo docker compose --env-file .env \
  -f docker/docker-compose.dank-wordpress.yml -p dank-store-test)
wp() { "${dc[@]}" run --rm --no-deps -T dank-wordpress-cli "$@"; }
"${dc[@]}" exec -T dank-wordpress-db sh -ec \
  'exec mariadb-dump -u root -p"$MARIADB_ROOT_PASSWORD" --single-transaction --routines --triggers "$MARIADB_DATABASE"' \
  > "$DOMAIN_BACKUP/wordpress.sql"
test -s "$DOMAIN_BACKUP/wordpress.sql"
wp option get home > "$DOMAIN_BACKUP/home.txt"
wp option get siteurl > "$DOMAIN_BACKUP/siteurl.txt"
sudo docker exec erpnext-backend cat \
  /home/frappe/frappe-bench/sites/erp.danks.store/site_config.json \
  > "$DOMAIN_BACKUP/erp-site-config.json"
sudo docker exec erpnext-backend bench --site erp.danks.store backup
bash erpnext/deploy.sh erp.danks.store commerce
"${dc[@]}" up -d --no-deps --force-recreate dank-wordpress
printf 'Private backup: %s\n' "$DOMAIN_BACKUP"
```

Expect successful ERP deployment and the same WordPress container running. The bind-mounted
customer plugin now supports net. Configuration and URL changes have not happened yet.
Use the existing off-host backup process to retain the private backup.

## 2. Check external connections

Add `https://dankmushrooms.net/*` to the Google Maps browser key's permitted websites, retaining
the old host temporarily. Keep the separate server key's restrictions intact.
Review the installed Clover gateway and Woo Shipping connection for hostname-specific settings;
keep merchant credentials and environment unchanged. No live charge or postage purchase is
part of this hostname procedure. Keep the existing checkout access restriction on the net host.

## 3. Change the URL and customer API transport

Use the same shell and verified existing net HTTPS vhost. The configuration helper validates
the enabled production pairing, makes a private first-use backup and preserves credentials,
logical site, signup/projection flags and approved customer IDs.

```bash
bash scripts/commerce-configure-woo-signup.sh --storefront-domain
wp option update home https://dankmushrooms.net
wp option update siteurl https://dankmushrooms.net
wp cache flush
wp option get home
wp option get siteurl
for host in shop-test.danks.store dankmushrooms.net; do
  curl --silent --show-error --max-time 10 --output /dev/null \
    --write-out '%{http_code} %{url_effective} redirect=%{redirect_url}\n' \
    "https://$host/my-account/"
done
```

Both options must be HTTPS net. Sign in again at https://dankmushrooms.net/wp-admin/.
Keep the old customer webhook URL and direct NGINX location intact. No new receiver is needed.
Check My Account, media, shipping rates/pickup/local delivery and owner-address SMTP delivery.
Use an existing linked owner-controlled account for one name edit in Woo and one in its ERP
Contact. Verify the same Customer/link updates in both directions, then restore the test edit.
Keep deployment verification separate from an actual live checkout test.

## 4. Preview embedded storefront links, then apply

The existing old host remains available for assets. This scoped helper changes post content and
excerpts only. It excludes orders, options, metadata and GUIDs, handles serialized arrays, and
stops on serialized objects. It replaces exact HTTPS shop-test URLs only; inspect HTTP links,
menus, widgets, theme settings and custom fields individually in WordPress.

```bash
"${dc[@]}" run --rm --no-deps -T \
  -v "$PWD/scripts/commerce_wordpress_hostname.php:/tmp/commerce_wordpress_hostname.php:ro" \
  dank-wordpress-cli eval-file /tmp/commerce_wordpress_hostname.php preview
```

Review `preview changed_content_rows=N`. To apply with a private compare-before-restore journal:

```bash
sudo install -d -m 700 -o 33 -g 33 "$DOMAIN_BACKUP/content-private"
"${dc[@]}" run --rm --no-deps -T \
  -v "$PWD/scripts/commerce_wordpress_hostname.php:/tmp/commerce_wordpress_hostname.php:ro" \
  -v "$DOMAIN_BACKUP/content-private:/hostname-private" \
  dank-wordpress-cli eval-file /tmp/commerce_wordpress_hostname.php \
  apply /hostname-private/content.json
```

Never overwrite the journal. Return only changed-row counts and non-secret status output.

## 5. Customer and order deltas after the rename

Ecwid is still accepting orders, so take a fresh export after this step and a final catch-up
immediately after pausing Ecwid checkout at cutover. Compare stable Ecwid customer/order IDs
against prior imports; match existing ERP customers and Woo accounts without creating duplicates.
Use dankmushrooms.net as the Woo transport, retaining the existing logical store identities.

Include the newest Coco purchaser and the cash-on-delivery web order. Preserve its actual payment
state, Delivered status, MP-assigned products and physical movements. Delivered alone is not proof
of cash receipt. Historical order import must not charge a card, send customer mail, reserve or
deduct inventory again, create a second shipment, or duplicate financial documents. Keep any ERP
cash invoice/receipt that has not yet been posted explicitly pending review. Never clear the
other open order's hold merely because this order was delivered.

This hostname release does not implement historical Woo order import or the unfinished live
order stack. Review a customer/order delta preview before writing it, and document which system
needs each historical record. Do not replay delivered Ecwid orders through live Woo intake.

## Roll back this hostname only

Use the same shell and DOMAIN_BACKUP directory. Restore the two saved WordPress options and
only the ERP transport setting; preserve newer database records and configuration changes.

```bash
wp option update home "$(cat "$DOMAIN_BACKUP/home.txt")"
wp option update siteurl "$(cat "$DOMAIN_BACKUP/siteurl.txt")"
wp cache flush
bash scripts/commerce-configure-woo-signup.sh --restore-storefront-domain
```

If content was applied, restore only journaled fields. The helper refuses rows changed since apply:

```bash
"${dc[@]}" run --rm --no-deps -T \
  -v "$PWD/scripts/commerce_wordpress_hostname.php:/tmp/commerce_wordpress_hostname.php:ro" \
  -v "$DOMAIN_BACKUP/content-private:/hostname-private" \
  dank-wordpress-cli eval-file /tmp/commerce_wordpress_hostname.php \
  restore /hostname-private/content.json
```

Do not restore the entire WordPress database or site_config over new orders or edits. Leave both
existing HTTPS vhosts serving the same installation, and verify customer synchronization again.
