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

## 5. Customer completion and deferred order history

Owner decision on 2026-11-22: do not import historical Ecwid orders for this cutover.
The production audit found one refunded Woo test order and no ERP Sales Orders, Sales Invoices,
historical order migration identities or commerce order crosswalks. Keep Ecwid exports privately
for reference. Do not replay order `2XCJD` or any delivered Ecwid order through live Woo intake.
Any missing cash accounting remains a separate reviewed accounting task.

Eight real purchasing customers have ERP records. Seven have linked Woo customer accounts;
the existing administrator account remains unchanged and unlinked because the current profile
sync supports customer-role accounts only. No welcome/reset emails were requested during import.

### Cloudflare 403 / error 1010 after the hostname change

The production ERP container resolved the net hostname through Cloudflare. Its default Python
user agent received HTTP 403 / error 1010, while the same authenticated customer GET with an
explicit RootedOps agent returned HTTP 200. The old hostname was direct and returned 200.
Commerce 0.3.8 identifies customer GET/PUT and shared API requests as `RootedOps-Commerce/1.0`.
Deploy the committed sources; do not patch the running container or disable Cloudflare protection.

If the transport was temporarily restored to the old host, deploy first, then run:

```bash
bash erpnext/deploy.sh erp.danks.store commerce
bash scripts/commerce-configure-woo-signup.sh --storefront-domain
sudo docker exec -i -w /home/frappe/frappe-bench/sites erpnext-backend \
  /home/frappe/frappe-bench/env/bin/python - <<'PY'
import frappe
from rootedops_commerce import customer_sync as sync
frappe.init(site="erp.danks.store", sites_path=".")
frappe.connect()
frappe.set_user("Administrator")
try:
    site = "shop-test.danks.store"
    conf = sync.settings(site)
    if conf.get("woo_origin") != "https://dankmushrooms.net":
        raise RuntimeError("Expected the reviewed net transport")
    for customer_id in ("5", "6", "7", "8", "9", "10", "11"):
        customer = sync.woo_request(site, customer_id, conf)
        print("Woo", customer_id, "authenticated read: OK")
finally:
    frappe.db.rollback()
    frappe.destroy()
PY
```

These are authenticated reads only. If any fails, restore only customer transport using
`bash scripts/commerce-configure-woo-signup.sh --restore-storefront-domain` and diagnose the
response before resuming. Keep WordPress home/siteurl on the net hostname. Keep the logical
store identity `shop-test.danks.store`, customer webhook route and links unchanged.

After successful reads, test an account name edit in an existing owner-controlled linked
customer from Woo to ERP, then its Contact from ERP to Woo after the scheduler runs. Restore
the test values. The API reads do not by themselves prove projection writes. Keep the old
hostname until these pass and remaining cutover integrations have been checked.

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
