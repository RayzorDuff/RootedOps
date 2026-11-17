# Dank Mushrooms WooCommerce cutover and rollback

Use the existing `dank-store-test` Compose project and volumes, `erp.danks.store`
and the existing MushroomProcess database. The public hostname becomes
`danks.store`. The approved launch assumes no Ecwid catalog, order or customer
deltas. Retain the source exports and historical IDs. Use the current Woo tax
settings as the checkout candidate.

## 1. Review and deploy code

The stack is RootedOps **#111 → #112 → #113 → #115 → #116**.
MushroomProcess **#115** can merge independently and must be deployed before
the shipment step. RootedOps **#114** branches from **#113** and can merge
independently of the shipment branch. Its settlement pilot remains a
separate, draft-only test. Merge the storefront cutover/checks PR independently.
For stacked PRs, preserve ancestry with merge commits and retarget the next PR
to main after its base merges. If using squash, rebase each child and verify its
diff and CI first.

On the Linode, use the existing project paths, private environment, deployed
ERP app image procedure and Compose overrides. Check the running service
rather than guessing a staging container. Use the same project name and
same database and HTML volumes after the hostname change.

```bash
cd ~/RootedOps
git switch main
git pull --ff-only
sudo docker ps --filter label=com.docker.compose.service=erpnext-backend \
  --format '{{.Names}} {{.Status}} {{.Ports}}'
curl -fsS --max-time 10 https://erp.danks.store/api/method/ping
```

Record the ERP backend name as `ERP_BACKEND`, and record the exact ERP, MP and
Woo database identities. Install the merged RootedOps ERP image using the
same deployment command and private flags used for the deployed project.
Validate the new app is importable, then apply additive ERP changes. For the
usual RootedOps deployment, run the existing commerce-only deploy command
after the backup and use its actual resulting container name for verification.

```bash
sudo docker exec "$ERP_BACKEND" bench --site erp.danks.store list-apps
sudo docker exec "$ERP_BACKEND" bench --site erp.danks.store backup --with-files
./erpnext/deploy.sh erp.danks.store commerce
# The commerce deploy runs the migration. Verify the resulting ERP service before proceeding.
sudo docker exec "$ERP_BACKEND" bench --site erp.danks.store list-apps

# MP_REPO points at the merged MushroomProcess checkout.
# MP_ADMIN_DSN is the private operator DSN, distinct from the worker credential.
psql "$MP_ADMIN_DSN" -X -v ON_ERROR_STOP=1 -c \
  "SELECT current_database(), to_regprocedure('public.mp_commerce_ingest(jsonb)'), to_regprocedure('public.mp_commerce_confirm_reservation(text,text,text)')"
psql "$MP_ADMIN_DSN" -X -v ON_ERROR_STOP=1 \
  -f "$MP_REPO/schema/pgsql/055_commerce_atomic_shipment.sql"
psql "$MP_ADMIN_DSN" -X -Atc \
  "SELECT to_regprocedure('public.mp_commerce_ship_products(text,text,text,text,jsonb)')"
```

Verify 051–054 and the existing MP ledger first. If a prerequisite is absent,
compare deployed migration history and apply only the missing reviewed migrations.
Use the operational shipping role for movement and the order worker role for
intake/payment/link/confirmation. Determine role grants from the existing private
MP deployment, including underlying invoker-rights table/function permissions.

## 2. Preserve the rollback baseline and close competing checkout

Run on the active Linode using its actual Dank Compose arguments. Protect the
backup directory and store encrypted copies off the host. Verify the database
dump and tar listing before routing changes. Record the corresponding ERP
backup files, MP export, current DNS records/TTL, NGINX configuration and
Woo webhook/FluentSMTP settings. Verify restore through a disposable target.

```bash
umask 077
cutover_backup="$HOME/commerce-migration/cutover-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$cutover_backup"
dc=(sudo docker compose --env-file .env -f docker/docker-compose.dank-wordpress.yml)
wp() { "${dc[@]}" run --rm --no-deps -T dank-wordpress-cli "$@"; }
wp option get home
wp option get siteurl
"${dc[@]}" exec -T dank-wordpress-db sh -c \
  'MYSQL_PWD="$MARIADB_ROOT_PASSWORD" exec mariadb-dump --single-transaction -u root "$MARIADB_DATABASE"' \
  > "$cutover_backup/woo.sql"
"${dc[@]}" exec -T dank-wordpress tar -C /var/www/html -czf - . \
  > "$cutover_backup/woo-files.tar.gz"
pg_dump --format=custom "$MP_ADMIN_DSN" > "$cutover_backup/mp.dump"
sudo nginx -T > "$cutover_backup/nginx.txt" 2>&1
tar -tzf "$cutover_backup/woo-files.tar.gz" >/dev/null
pg_restore -l "$cutover_backup/mp.dump" >/dev/null
sha256sum "$cutover_backup/"{woo.sql,woo-files.tar.gz,mp.dump,nginx.txt} \
  > "$cutover_backup/SHA256SUMS"
```

Before changing DNS, preserve the saved Ecwid sitemap and audit both ad feed
configuration records below. Review published opening stock ownership and Woo
settings without opening sales. At the switch, open **Ecwid → Settings → General → Store Profile**, enable
storefront maintenance mode (close the storefront), and verify a signed-out
browser cannot purchase through the
apex or the old Ecwid storefront URL. Keep the Ecwid account and restoration
path available. [Ecwid storefront maintenance steps](https://support.ecwid.com/hc/en-us/articles/207101209-Closing-your-storefront-for-maintenance) Pause Woo stock/projection schedules and walk through cashier
and market sales with staff. Confirm there is no independent channel selling the
same MP pool during the controlled opening window. Existing Ecwid orders may
still need fulfillment or stock holds and must be included in opening availability.

## 3. Restrict access while switching HTTPS and Woo URLs

Prepare the apex TLS server block using the existing Dank vhost upstream
(`127.0.0.1:8097` in the repository configuration; verify with `ss`).
Obtain the final certificate for `danks.store` through the existing
Certbot/ACME procedure. Use DNS validation when HTTP still goes to Ecwid.
Protect the apex server before DNS changes. At server level allow only the
owner's verified public IP and deny other visitors during the acceptance window.
If using a CDN or reverse proxy, validate the trusted real-IP configuration and
verify two independent clients. Keep the `shop-test` vhost restricted during
the switch too and ensure it cannot accept checkout against the same DB.

Add the exact order endpoint to the **apex TLS** block once the worker is
listening. Review the sender egress IP on the Linode and use it in this
location. If the host cannot reach this route using the final DNS/HTTPS path,
resolve that route before the first charge.

```nginx
location = /webhooks/woocommerce/danks.store {
    allow 127.0.0.1;
    allow <reviewed-Linode-Woo-egress-IP>;
    deny all;
    limit_except POST { deny all; }
    proxy_set_header X-WC-Webhook-Signature $http_x_wc_webhook_signature;
    proxy_pass http://127.0.0.1:8102;
}
```

If the Clover extension requires any public server callback, identify its exact
route and verify its auth and behavior before opening an exception. The owner
browser must retain access to the Woo order-pay and return URLs; validate this
during the gateway preflight. Restricting the whole Woo vhost also covers Store
API, classic checkout, pay-for-order, and other checkout entry points.

```bash
sudo nginx -t && sudo systemctl reload nginx
wp option update home https://danks.store
wp option update siteurl https://danks.store
wp option update rootedops_ecwid_redirect_permanent 0
wp option get home
wp option get siteurl
wp search-replace 'https://shop-test.danks.store' 'https://danks.store' \
  "$(wp db prefix)options" "$(wp db prefix)posts" --skip-columns=guid --dry-run
```

Update the inactive/reviewed Dank theme through WordPress Admin or install the
theme ZIP from the repository [theme deployment instructions](dank-storefront-staging.md).
Verify the active theme before proceeding. Review the URL replacement plan. Correct stale storefront URLs in current
menus, theme/content and integrations. Scope writes to reviewed live fields and
preserve historical references and source archives. Clear the Woo/site/CDN
cache as applicable. Verify the final Host header/forwarded HTTPS scheme
locally, then change the existing apex DNS record to the reviewed Linode/CDN
target. Test TLS, final checkout URLs and redirects from the allowed client.
For the initial acceptance window, prefer leaving DNS and unrelated sites
out of service restarts.

## 4. Set and verify opening stock

Available recurring RootedOps and MushroomProcess n8n Woo writers are
hidden-draft/shop-test scoped. Use a bounded manual opening from approved,
reservation-adjusted MP quantities. A zero or excluded SKU stays unavailable.
Use one Woo listing per physical Item/strain pool for this window. Reserve or
otherwise reconcile outstanding Ecwid commitments in MP before counting
opening stock. Document any other POS inventory committed from those pools.

Export the authoritative MP candidates without changing stock:

```bash
psql "$MP_ADMIN_DSN" -X --csv -v ON_ERROR_STOP=1 -c "
  SELECT c.ecommerce_id AS mp_id, c.external_product_id, c.external_variation_id,
         c.external_sku AS sku, c.erp_item_code, c.item_id, c.strain_id,
         c.item_id::text || ':' || coalesce(c.strain_id::text, 'none') AS pool_key,
         i.available_quantity AS mp_available
  FROM public.mp_ecommerce_catalog_inventory() c
  JOIN public.mp_commerce_inventory() i USING (ecommerce_id)
  WHERE c.provider='woocommerce' AND c.site_key='danks.store'
  ORDER BY c.ecommerce_id" > "$cutover_backup/woo-mp-opening.csv"
```

An empty or incomplete export means the final-host operational mappings must
be reviewed in MP. Preserve the historical Ecwid maps. Ensure each approved
Woo product/variation and exact SKU resolves to one enabled MP row at
`site_key=danks.store` with the reviewed ERP Item code. Compare the physical
pool (`item_id,strain_id`) across rows so stock is assigned only once.

Create the private opening CSV from those reviewed records. Header:
`woo_id,parent_woo_id,mp_id,sku,source_key,pool_key,mp_available`. Use the exact Woo
`_rootedops_source_key` on the owned product or variation parent. Leave the
parent column blank for simple products. Copy the exact MP pool key from the
SQL export. While checkout stays closed, set
those quantities on their exact Woo Items in **Products → Inventory**
(or the variation inventory section), enable **Manage stock**, and set
**Backorders → Do not allow**. Verify every row with a read-only Woo API
credential, loaded privately as `WC_AUTHORIZATION`:

```bash
python scripts/commerce_cutover_check.py stock "$OPENING_CSV" --host danks.store
```

Review each mismatch and rerun the check with a fresh MP snapshot before
unrestricting checkout. Once paid Woo selling begins, Woo decrements stock,
and MP owns reservations and fulfillment. Reopen only with an accepted
ongoing order admission and reconciliation process. This single-order worker
intentionally ignores later IDs. A wider automated admission or a named
operator processing each sale against MP is required for public checkout.
Pause checkout for manual Woo quantity corrections, reconcile accepted Woo
orders and holds, and verify the new Woo counts before reopening.

## 5. Compare legacy storefront and QR paths

Use the saved Ecwid sitemap (42 legacy member paths). The repository also
contains the 42 legacy locators captured from the public Ecwid sitemap before
the switch. Set `ECWID_SITEMAP=doc/fixtures/dank-ecwid-legacy-sitemap.xml` if the
original operator copy is unavailable. The accepted checked-in manifest is
`doc/fixtures/dank-ecwid-staging-redirects.csv`. Recreate it if the storefront
destinations change before the switch:

```bash
python scripts/commerce_cutover_check.py redirects "$ECWID_SITEMAP" \
  --host shop-test.danks.store > "$cutover_backup/staging-expected.csv"
```

Baseline: 29 legacy paths redirect to Woo 200, 12 generic dollar listings
remain 404, and Miscellaneous remains 404 pending a useful replacement.
The staging rerun against the saved locators reproduced all 42 outcomes.
One previously documented printed product URL returned 404 in a remote probe.
Use the current printed samples and verify the live QR service and mappings
before treating labels as accepted.
Review intended exact Woo slugs in the manifest. Keep `decision` for
Miscellaneous until the owner chooses a mapped category or permanent 404.
Keep 302 during the switch. Set `QR_LABEL_CSV` to a separate `url,final_path`
CSV for real printed product labels. Sample a gourmet product, a kit or
mycology product, and another active SKU. Test the printed QR URLs exactly,
including the existing redirect service if it resolves via a legacy path.

```bash
python scripts/commerce_cutover_check.py redirects "$ECWID_SITEMAP" \
  --expected doc/fixtures/dank-ecwid-staging-redirects.csv --qr "$QR_LABEL_CSV"
# Only after acceptance, replace temporary redirects and repeat verification.
wp option update rootedops_ecwid_redirect_permanent 1
python scripts/commerce_cutover_check.py redirects "$ECWID_SITEMAP" \
  --expected doc/fixtures/dank-ecwid-staging-redirects.csv --qr "$QR_LABEL_CSV" --redirect-status 301
# To restore temporary redirects if needed:
wp option update rootedops_ecwid_redirect_permanent 0
```

## 6. Verify checkout and configure the single-order integration

From the approved client, use distinct shipped, pickup, and local-delivery
test carts and record cart subtotal, discounts, shipping, tax, and grand total.
Compare a shipped address eligible for USPS, pickup details with no shipping
charge, and a local delivery address on each side of the configured boundary.
Use the current tax candidate and record the amount shown on each cart.
In FluentSMTP, review the From identity and deliver a test email to an owner
mailbox. Confirm order receipt delivery from the actual purchase. In
**WooCommerce → Settings → Payments → Clover**, verify the official
extension, live mode, exact active merchant and Ecommerce credentials in
the private UI. Review API checkout/order-pay compatibility. Merchant secrets
and raw processor data stay private.

Pause existing customer signal hooks before the URL change. At the final URL,
retain the same WP database/user IDs. Update the private ERP
`commerce_customer_sync` settings for `woo_site: "danks.store"`,
`production_erp_pilot: true`, `same_woo_installation: true`, and the reviewed
customer IDs and final-site Woo REST authorization. Verify the owner's numeric
Woo ID still refers to the same account. The ERP key remains in the old
installation namespace and conflicting final-site links go to review. When
resuming the customer worker, add the final site to `customer_sites` with
`erp_base_url: "https://erp.danks.store"`, `production_erp_pilot: true`
and its dedicated secret, point the customer hook at
`/webhooks/woocommerce-customer/danks.store`, and run the existing
`runtime.py work-customers-once --config "$CUSTOMER_CONFIG" --customer-site danks.store`.
Keep signup provisioning/projector settings scoped to the owner-approved plan.

Record a cutoff before creating the owner's **new** order.

```bash
date -u +%FT%T
```

Create the approved pending order on the final Woo instance, with the selected
customer, product, shipping method and reviewed total. Use the Woo customer
payment link for the actual owner purchase. Record the new numeric ID and
display order number, confirm the order was created after the cutoff, and
keep broad publicly accessible checkout restricted.

Create a mode-0600 worker JSON at `LIVE_ORDER_CONFIG`. Supply the actual approved
identities. For a variation, use the variation ID as the mapping key and its
parent as `product_id`. Supply the reviewed destination tax quote for this order
under `draft_policy.tax_quotes[woo_order_id]`; an actual zero-tax scenario uses
an explicit reviewed zero quote. The same Woo candidate totals are used
by the ERP verification, including shipping. The schema and evidence fields
are in [the mapped-draft runbook](commerce-unpaid-order-pilot.md#reviewed-mapping-follow-up)
and `rootedops_commerce/tax_contract.py`.

```json
{
  "enabled": true,
  "woo_order_id": 9001,
  "not_before_gmt": "2026-11-16T23:00:00",
  "inbox_database": "dank_woo_order_inbox",
  "mp_database": "<verified current MP database>",
  "approved_item_codes": ["<reviewed ERP Item>"],
  "mappings": {
    "501": {"product_id": 501, "sku": "<exact Woo SKU>", "ecommerce_id": 123, "erp_item_code": "<reviewed ERP Item>"}
  },
  "draft_policy": {
    "company": "<ERP company>", "currency": "USD", "selling_price_list": "<ERP price list>",
    "guest_customer": "<reviewed guest Customer>", "shipping_item": "<ERP nonstock shipping Item>",
    "tax_quotes": {}
  }
}
```

Put the same approved order and cutoff in private ERP site config under
`commerce_live_order`, with `enabled: true` and `capture_enabled: false`.
Set `commerce_order_shipping_item` and the existing reviewed
`commerce_tax_provider`, `commerce_tax_item_class_map`, and
`commerce_tax_account_map` for the quote. In `commerce_clover_capture_pilot`,
configure `enabled: true`, `merchant_id`, `company`, `clearing_account` and the
shared private `evidence_hmac`. The live capture remains off until the exact
charge is approved by both targets. Configure `commerce_mp_fulfillment_pilot`
with `enabled: true` and private `movement_hmac` only at the shipment step.

Apply reviewed settings through a mode-0600 JSON file at
`ERP_LAUNCH_PATCH`. Include only the cutover keys you intend to modify. The
command merges top-level dictionaries one level deep, retaining unrelated keys
and previously set private values. Supply a fresh patch for capture, fulfillment
and pause. Keep ERP credentials and proof keys out of shell history.

```bash
sudo docker exec -i --user frappe "$ERP_BACKEND" python3 -c '
import json, os, pathlib, sys, tempfile
site = pathlib.Path("/home/frappe/frappe-bench/sites/erp.danks.store/site_config.json")
new = json.load(sys.stdin)
keys = {"commerce_live_order", "commerce_customer_sync", "commerce_order_shipping_item",
        "commerce_tax_provider", "commerce_tax_item_class_map", "commerce_tax_account_map",
        "commerce_clover_capture_pilot", "commerce_mp_fulfillment_pilot"}
if not isinstance(new, dict) or not set(new) <= keys:
    raise ValueError("Review patch keys")
current = json.loads(site.read_text())
for key, value in new.items():
    if isinstance(value, dict):
        current[key] = {**(current.get(key) or {}), **value}
    else:
        current[key] = value
with tempfile.NamedTemporaryFile(mode="w", dir=site.parent, delete=False) as out:
    json.dump(current, out, indent=2)
    out.write(chr(10))
os.replace(out.name, site)
' < "$ERP_LAUNCH_PATCH"
```

Prepare a new dedicated Postgres inbox and its restricted role, separate
from MP. Use private DSNs `COMMERCE_LIVE_INBOX_DSN` and `COMMERCE_LIVE_MP_DSN`.
Include an explicit dbname in each worker DSN. Supply passwords through the
private PostgreSQL service/passfile rather than placing them in CLI arguments.
Confirm `SELECT current_database()` on each. Supply `ERP_AUTHORIZATION` from a
scoped Frappe user with Sales Manager and Accounts Manager permissions.
Use a new `COMMERCE_LIVE_WEBHOOK_SECRET` of at least 32 characters and separate
`COMMERCE_CAPTURE_EVIDENCE_KEY` and `COMMERCE_SHIPMENT_EVIDENCE_KEY` values matching
ERP config. Use a protected environment file and the project's Python worker
environment with psycopg 3. Prefer a supervised process on the Linode.

```bash
export COMMERCE_PRODUCTION_ORDER_PILOT=1
order() { python integrations/commerce/production_order.py "$@" --config "$LIVE_ORDER_CONFIG"; }
order init
sudo docker exec "$ERP_BACKEND" bench --site erp.danks.store set-config \
  --parse commerce_order_integration_enabled True
order serve --port 8102
```

In Woo, enable the **Order created** and **Order updated** v3 webhooks at
`https://danks.store/webhooks/woocommerce/danks.store` with the new secret.
Trigger a fresh, valid Woo save of the approved pending order after enabling.
Use the staging runbook's native Woo webhook setup method if the UI sends an
unsigned test ping. From the reviewed Woo sender network, expect HTTP 400 from
this unsigned check before placing an order:

```bash
curl -sS -o /dev/null -w '%{http_code}\n' \
  -H 'Content-Type: application/json' -d '{}' \
  https://danks.store/webhooks/woocommerce/danks.store
```

Confirm unsigned requests are rejected and authenticated
but unapproved IDs are ignored without a durable receipt. Avoid two distinct
Woo status changes within the same timestamp second. A same-second conflict
goes to review. In the worker shell with the same private env:

```bash
order work-once
order status
```

Expect one MP reservation and one ERP draft. For a reviewed dead letter, use
`order replay --event-id "$REVIEWED_EVENT_ID"` and rerun `order work-once`.
The replay command checks that the receipt belongs to the approved order. Validate the exact totals and link.
Submit the reviewed ERP Sales Order as the owner before capture posting.
Verify the selected ERP Items/default warehouse allow native order submission
and that the ERP stock reservation setting matches the MP-owned stock plan. Make one
owner-controlled purchase from the Woo payment link. Ensure Clover shows the live
capture for the same order, merchant, currency and amount. Add
`clover_charge_id` to both the private worker JSON and ERP `commerce_live_order`;
set ERP `capture_enabled: true`. Set `CLOVER_LIVE_MERCHANT_ID` and
`CLOVER_LIVE_PRIVATE_KEY` privately. Process the signed paid update and post:

```bash
order work-once
order status
order capture --posting-date "$REVIEWED_POSTING_DATE"
# Repeat the same verified capture command to verify durable identity.
order capture --posting-date "$REVIEWED_POSTING_DATE"
```

Record the Woo ID/display number, SHA receipt, Clover capture ID, MP hold, and
ERP Sales Order, Sales Invoice and Payment Entry. Expect exactly one set.
If a sandbox/failed/mismatched charge or a partial/full refund appears, review it
instead of creating a new payment. A dropped ERP response is safe to retry
using the same references. If a valid historical receipt entered review,
recheck actual Woo status, amounts and reserve state before taking any action.

For an actual owner fulfillment, use the reviewed product scan and a saved
movement reference. Use the private operational role DSN as `MP_SHIPPING_DSN`.

```bash
psql "$MP_SHIPPING_DSN" -X -v ON_ERROR_STOP=1 -v order_id="$WOO_ORDER_ID" \
  -v movement="$MOVEMENT_REFERENCE" -v lines="$SHIPMENT_LINES" <<'SQL'
SELECT public.mp_commerce_ship_products('woocommerce','danks.store',
                                        :'order_id', :'movement', :'lines'::jsonb);
SQL
order shipment --movement-reference "$MOVEMENT_REFERENCE"
order shipment --movement-reference "$MOVEMENT_REFERENCE"
```

`SHIPMENT_LINES` contains Woo `line_id` and numeric MP `product_ids`. The ERP
stock-neutral receipt should retain the same ID on replay. The native
disposable runs cover replay and cancellation of unshipped units. For a live
owner cancellation, follow the refund or void decision below and confirm that
an unshipped cancellation releases the hold. A shipped unit stays shipped.

## 7. Google and Meta transition

Before the switch, save privately: Merchant Center ID, linked Google Ads ID
and campaign/feed references, site claim, Ecwid data-source ID/type/feed label,
country/language and a sample export of exact offer IDs by variant and SKU.
Save Meta Business Portfolio, catalog, shop, Page and Instagram profile IDs,
Pixel/dataset and CAPI connection, catalog source ID and retailer/item IDs,
event `content_ids`, plus account roles and linked ads. Keep the current
configuration screenshots and exports available for rollback.

Reuse the existing eligible Merchant Center and Google Ads accounts with
[Google for WooCommerce](https://woocommerce.com/document/google-for-woocommerce/get-started/setup-and-configuration/).
Its product IDs normally use `gla_` plus the Woo ID. If maintaining old offer
IDs is valuable for campaign continuity, use a reviewed Woo-generated file/API
feed that emits the exact old offer ID and correct variant, language, feed
label and country, and verify a small test before replacing the source. Do
not assume reuse of an account preserves listing IDs.
[Google for WooCommerce ID behavior](https://woocommerce.com/document/google-for-woocommerce/faq/)

Select the existing Meta assets in
[Meta for WooCommerce](https://woocommerce.com/document/facebook-for-woocommerce/).
Before bulk sync, inspect whether the chosen connector actually preserves the
retailer ID and whether Pixel and CAPI `content_ids` match the new catalog
items. If IDs cannot be preserved, align catalog and event IDs together before
switching catalog ads. Avoid parallel tag installations that double-send
purchase events. Preserve the existing account ownership and Pixel/dataset.

After final HTTPS, use a simple product and a variation in each feed. Verify
canonical domain, exact item ID, price, stock, image, landing, shipping, and
absence of duplicate offers. Verify an allowed Meta event reaches the correct
dataset/catalog identity and Google diagnostics are clean. Move traffic to the
accepted Woo source. Pause Ecwid publishing by source, preserve its settings,
and verify remaining Woo listings and campaign links. Retire only the old
source after the owner confirms acceptance. If rollback is needed pause the
new source before re-enabling the old one.

## 8. Pause, refund and roll back

If totals, references, stock or mail diverge, keep Woo checkout restricted.
Pause the two Woo order webhooks and customer webhook if changing hosts. Stop
the order listener and any scheduled worker. Disable ERP order mutations:

```bash
sudo docker exec "$ERP_BACKEND" bench --site erp.danks.store set-config \
  --parse commerce_order_integration_enabled False
order status > "$cutover_backup/final-inbox-status.json"
```

Set `commerce_live_order.enabled` and `capture_enabled` false in private ERP
config and set worker JSON `enabled` false after capturing read-only evidence.
Preserve the Woo DB, checkout/payment references, ERP docs, MP holds and
inbox. Export and reconcile Woo orders taken during the window, including
any authorized but uncaptured or captured-but-unlinked charge. Record the
time and owner on each disposition and keep captured inventory excluded until
resolved.

For an unshipped captured order, follow [WooCommerce refund procedure](https://woocommerce.com/document/woocommerce-refunds/).
Verify the original Clover transaction and
any previous refunds. In the Woo order screen, use the **gateway refund** if
the installed Clover extension supports it and verifies success. Otherwise
refund the original charge once in the Clover merchant portal and record its
refund ID/amount as a **manual** refund in Woo. Check Clover before retrying an
ambiguous refund. Handle uncaptured authorizations through the processor's
reviewed void flow. Verify refund amount, currency, status, any ERP credit
note/payment reversal required by Accounting, and MP hold release. For a
shipped order the physical return must be handled separately in MP. Keep the
audit trail; order/payment automation routes refunds to review.

To return shoppers to Ecwid, verify Woo checkout is inaccessible, route the
apex back with the saved DNS/NGINX config, and reopen only the Ecwid intake.
Adjust available Ecwid stock for unresolved Woo commitments. If the old Woo
hostname is needed for admin access, update Woo home/siteurl in the same
database and restore the customer transport settings for that hostname.
Retain already-processed transactions in the ERP and MP databases. Use backups
for recovery or isolated comparison; a routing rollback does not restore an
old database over newly accepted orders.

## 9. Ecwid retirement

Once the owner approves live intake and feed replacement, verify the first
Clover payout against gross captures, actual fees/adjustments, and the bank
deposit. Include other Clover channel transactions in mixed funding. Use the
[funding evidence checklist](commerce-clover-funding.md#evidence-needed-from-the-merchant).
Confirm with the merchant/provider that the Woo live Ecommerce credentials,
merchant entitlement, rates, funding, portal access and refund rights remain
available **after Ecwid cancellation**. Keep retention exports, historical
URL/QR checks, references and a rollback decision on record before cancellation.
