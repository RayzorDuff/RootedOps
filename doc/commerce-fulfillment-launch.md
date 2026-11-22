# Woo order, inventory and MushroomProcess dispatch acceptance

Inventory compatibility update: use [the shared-pool owner handoff](commerce-inventory-owner-handoff.md) with the canonical hostname procedure. MP 058 is now deployed for Ecwid; the Woo follow-up 059 aligns picking/dispatch and the explicit cutover owner. Do not reapply 058 over newly installed Woo intake functions.

Canonical hostname update: use [dankmushrooms.net preparation](dankmushrooms-canonical-domain.md) before hosted acceptance. It supersedes older deployment prose naming danks.store as the primary website. Keep danks.store as the existing logical order identity. Ecwid keeps its current public routing until the later cutover.

The installed rehearsal uses `shop-test.danks.store`, production ERP at `erp.danks.store`, and the existing Linode. Use the same Woo installation for the final `dankmushrooms.net` hostname, retaining `danks.store` as its logical order identity. Disposable CI supplies development verification. Clover Flex and REST Pay Display are separate work.

## What runs automatically

Signed Woo webhooks are durably received before HTTP 202. The existing inbox tracks MP and ERP independently. Accepted ERP drafts and verified Clover captures retain the existing stable references and retry behavior. The ongoing review queue in #118 accepts multiple orders. The reviewed-order cycle continues their later snapshots after initial approval. Unknown items, customer links, tax quotes, money differences, refunds and conflicting snapshots need review. ERP Sales Order approval/submission and the initial financial/account mapping remain owner steps. This release uses the existing per-order review procedure for accounting. A receiver alone does not process that review queue.

After a confirmed paid order appears in MP, the operator scans its physical units into a package. Packing keeps the reservation and current location. Label/tracking preparation updates the package without dispatching. Confirm dispatch when the parcel leaves, pickup is handed over, or local delivery is completed. That transaction moves physical units, consumes their holds and creates one delivery row for each of Woo and ERP. A timer retries destinations independently and automatically publishes MP availability to reviewed published Woo IDs. A failed delivery stays visible and retries with the same movement reference. ERP records fulfillment in a stock-neutral Commerce External Receipt and its linked Commerce Order State quantities. MP commits the physical movement.

The new MP overlay adds a Woo section to the existing Fulfillment page. It preserves the existing Ecwid widgets/actions. Whole Lots count as one sellable unit, matching MP's current catalog COUNT model. Fractional weights and withdrawals from a manufacturing source require a separately reviewed quantity flow. Product scans and whole-Lot scans can share a package and its tracking record. Package references are stable and unique within the Woo store. Keep a reference on retries and use a new one for each additional package.

## Evidence and remaining hosted checks

The owner's production preflight found ERP commerce `0.3.4` and database `mushroomprocess_bridge`. Intake, MP availability, payment matching, and Product location movement exist. There is one active Shipped location. The ERP-link and shipment tables, reservation confirmation and shipment acknowledgment functions are absent. This is consistent with 054 pending. CI passing does not establish installed schema. Inspect `reservation_confirmed` and the migration footprint before applying 054, then 055, 056 and 057 in that order. Never replay the baseline SQL on this database.

Existing disposable evidence includes native signed Woo create/update webhooks returning 202, native MP reservations, native ERP drafts for guest and linked buyers, duplicate handling, cancellation release and ERP retry after a lost response. The new regressions add packing/dispatch separation, Product and whole-Lot partial fulfillment, concurrent-Woo commitment accounting, published stock, late-webhook protection and independent destination retry. Hosted label purchase, actual plugins, merchant capture, MP UI publication and email timing still require the owner.

## 1. Inspect installed Woo shipping capability

Run only this block first, on the production Linode. It reads URLs, plugins and shipping method identifiers. Paste its output. It prints no API keys or shipping configuration secrets.

```bash
(
  set -eu
  cd ~/RootedOps
  dc=(sudo docker compose --env-file .env -f docker/docker-compose.dank-wordpress.yml -p dank-store-test)
  wp() { "${dc[@]}" run --rm --no-deps -T dank-wordpress-cli "$@"; }
  wp option get home
  wp option get siteurl
  wp plugin list --fields=name,status,version --format=table
  wp eval 'foreach (WC_Shipping_Zones::get_zones() as $zone) { echo $zone["zone_name"]."\n"; foreach ($zone["shipping_methods"] as $method) { echo "  ".$method->id." enabled=".$method->enabled."\n"; } }'
)
```

Success is the current shop-test URLs, the installed plugin/version list, and expected shipping methods. Stop and share a missing CLI/service error. Do not install a label plugin yet. The USPS rate extension and a label purchasing extension have different capabilities. The installed list determines the next account/setup instructions. WooCommerce Shipping, when present, uses a connected WordPress.com account and saved payment method for postage. Label purchasing is an explicit paid operator action. [USPS rate documentation](https://woocommerce.com/document/usps-shipping-method/) · [WooCommerce Shipping labels](https://woocommerce.com/document/woocommerce-shipping/)

The MP button resolves the exact numeric order's `get_edit_order_url()` through an authenticated Woo endpoint, then opens that URL in a new tab. WordPress handles the user's login and permissions. Select Create shipping label on that order when its installed extension offers it. An order URL does not preselect the MP package's lines. Select the actual package contents yourself. Keep the label-purchase option to mark the order completed switched off. The MP plugin also rejects premature completion for managed orders. Inspect label-provider state before retrying any purchase that timed out, because the postage may have been purchased already.

Tracking retrieval through an installed label plugin has not been verified. The initial supported path records carrier, service, tracking number, label status and actual USD postage in MP. The fields belong to one package. A reprint or tracking edit never dispatches inventory. A voided label cannot authorize postal dispatch. After dispatch a replacement tracking record queues a Woo metadata refresh with the same physical movement. MP's tracking is displayed on Woo order details and the normal completed-order email. Partial dispatch updates the order without a separate customer email. The completed-order email is triggered when every required unit is acknowledged. Disable label-plugin completion/notification toggles that would send an earlier duplicate notification, then test this against the installed extension and FluentSMTP.

## 2. Merge and back up

Review the stack in this order, retargeting children after their parent merges. RootedOps #111 → #112 → #113 → #115 → #116 → #118 → #119 → #120. Retarget each child after its parent merges. If a parent is squash-merged, rebase its child before merging. RootedOps #117 contains the independent final-host routing/redirect/feed runbook. MushroomProcess #115 → #116 must be merged and deployed before activating RootedOps #119/#120 publication. Follow the repository owner’s reviewed promotion from main to the production branch. RootedOps #114 remains the settlement/fee track. Preserve the current ERP/customer-sync worker, timer and Woo hooks.

Use blocks A3–A5 in [the Linode runbook](dank-woocommerce-linode.md) to update the clean checkout and verify Woo, ERP and MP backups. Keep recovery copies off-host. Save the current private settings, worker unit files and NGINX configuration. Stop if a backup or archive check fails. Merge and backup precede production migration and service changes.

## 3. Verify the migration footprint

Run on the Linode after backups. This is read-only.

```bash
sudo docker exec -i mushroomprocess-bridge-postgres sh -ec \
  'exec psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' <<'SQL'
SELECT current_database() AS database,
 to_regclass('public.mp_commerce_erp_links') AS erp_links,
 to_regclass('public.mp_commerce_shipments') AS shipments,
 to_regclass('public.mp_commerce_packages') AS packages,
 to_regclass('public.mp_commerce_lot_picks') AS lot_picks,
 to_regprocedure('public.mp_lot_set_location(bigint,bigint)') AS lot_move,
 EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema='public'
   AND table_name='mp_commerce_orders' AND column_name='reservation_confirmed') AS confirmation_column;
SQL
```

With the reported baseline, both 054 tables and the confirmation column should be absent. A partial footprint needs inspection before proceeding. `MP_REPO` below must be the reviewed, merged MushroomProcess checkout, with the new SQL files. `MP_ADMIN_DSN` must privately identify the same `mushroomprocess_bridge` database and its migration owner.

```bash
test "$(psql "$MP_ADMIN_DSN" -X -v ON_ERROR_STOP=1 -Atc 'SELECT current_database()')" = mushroomprocess_bridge &&
psql "$MP_ADMIN_DSN" -X -v ON_ERROR_STOP=1 -f "$MP_REPO/schema/pgsql/054_commerce_operational_bridge.sql" &&
psql "$MP_ADMIN_DSN" -X -v ON_ERROR_STOP=1 -f "$MP_REPO/schema/pgsql/055_commerce_atomic_shipment.sql"
```

Stop on any SQL error. Run only the missing, reviewed migrations. Next run the new package migrations, once each.

```bash
psql "$MP_ADMIN_DSN" -X -v ON_ERROR_STOP=1 -f "$MP_REPO/schema/pgsql/056_commerce_pack_dispatch.sql" &&
psql "$MP_ADMIN_DSN" -X -v ON_ERROR_STOP=1 -f "$MP_REPO/schema/pgsql/057_commerce_lot_dispatch.sql" &&
psql "$MP_ADMIN_DSN" -X -v ON_ERROR_STOP=1 -c "SELECT
 to_regprocedure('public.mp_commerce_confirm_reservation(text,text,text)') AS confirmation,
 to_regprocedure('public.mp_commerce_dispatch(text,text,text)') AS dispatch,
 to_regprocedure('public.mp_commerce_pick_lot(jsonb)') AS lot_pick,
 to_regclass('public.mp_commerce_shipped_units') AS physical_units"
```

Success prints all four identities. Stop on missing objects or unexpected roles. These functions revoke public execution. Use the existing trusted database service roles. For separate service roles, the checked-in grant script below adds the commerce permissions. The fulfillment role must retain its existing MP physical-movement and location-link permissions. Confirm privileges with the actual worker/n8n connections before activating them. The new trigger guards use fixed search paths and read only package allocation state. They protect existing applications without requiring public access to the new tables.

Run the grants on the Linode only after verifying the actual worker and n8n database role names. Role names are identifiers, with no passwords in this command.

```bash
psql "$MP_ADMIN_DSN" -X -v ON_ERROR_STOP=1 \
  -v worker_role="$VERIFIED_COMMERCE_WORKER_ROLE" \
  -v fulfillment_role="$VERIFIED_MP_N8N_ROLE" \
  -f "$MP_REPO/schema/pgsql/ops/commerce_role_grants.sql"
```

Success commits the grants. Stop on an unknown role or failed grant. Do not grant the MP service permissions to the signed HTTP inbox role.

## 4. Deploy the code, keeping features disabled

Run the reviewed ERP commerce deployment from the Linode checkout. It uses the production ERP site.

```bash
cd ~/RootedOps
./erpnext/deploy.sh erp.danks.store commerce &&
curl -fsS --max-time 10 https://erp.danks.store/api/method/ping
```

Success is deployment validation and pong. Stop on failure. Follow the existing commerce-worker setup in the Linode runbook. Use `woo_origin: https://shop-test.danks.store` in its private config during rehearsal. Keep logical order identity `woocommerce / danks.store / numeric ID` for the same Woo database across both hostnames. The Woo delivery URL uses that configured canonical site key. The order's canonical identity can resolve the existing shop-test Customer link before and after the hostname switch. Enable the reviewed same-installation flag below after deploying commerce 0.3.5. It retains the current customer worker hostname and all other private settings.

```bash
sudo docker exec -i --user frappe erpnext-backend python3 - same-installation \
  < scripts/commerce_live_approve.py
```

Success prints ERP same-installation applied. Stop on a missing/mismatched customer configuration. The registered buyer's canonical Woo ID must resolve to its existing Customer. Never relink a customer by matching names or create another ERP Customer for the hostname switch.

Add the following private worker settings using actual reviewed IDs. The worker validates SKU, MP catalog ID, exact Woo ID, ownership and unique physical pool. The variation ID goes in `woo_id` for a variation.

```json
{
  "publication_enabled": false,
  "woo_origin": "https://shop-test.danks.store",
  "published_inventory": [
    {"ecommerce_id": 123, "woo_id": 501, "sku": "REPLACE", "source_key": "REPLACE"}
  ]
}
```

Store `WOO_MP_AUTHORIZATION` privately as the Basic authorization header for a dedicated WordPress application-password user with Woo management permission. Keep the exact hostname allowlist. Set `DANK_MP_WOO_ENABLED=0` initially. Set `DANK_MP_WOO_CUTOFF` to the reviewed UTC epoch for new accepted orders, matching the receiver's GMT cutoff. Existing historical/sandbox orders predate it. The compose mount supplies the disabled plugin. In a coordinated store window, recreate only the existing WordPress service after reviewing the compose change. Keep its project/volumes and customer webhook setting.

```bash
sudo docker compose --env-file .env -f docker/docker-compose.dank-wordpress.yml \
  -p dank-store-test up -d --no-deps dank-wordpress
```

Success is the same store and volumes, healthy My Account and customer hooks. Stop if the canonical URL, theme or customer synchronization changes unexpectedly. Set the private enable flag only after the reviewed mappings, cutoff, endpoint permissions and supervised worker are ready. Recreate this same service to load the setting.

Import the inactive `MushroomProcess - Woo Pack and Dispatch - PGSQL.json`. Bind its PostgreSQL credential to the verified MP database. Configure the Header Auth credential named MushroomProcess Commerce Fulfillment with a new private `X-MP-Commerce-Key`. Set `MP_COMMERCE_FULFILLMENT_ENABLED=true` and `MP_COMMERCE_WOO_ORIGIN=https://shop-test.danks.store` in the n8n environment. Bind Woo MP publication Basic Auth to the application-password user. Coordinate any n8n restart with its other active workflows.

Render the application overlay from the MushroomProcess checkout, then import it using your normal Appsmith publication procedure. Create the output directory first if it is absent.

```bash
umask 077
mkdir -p "$HOME/commerce-migration"
python3 "$MP_REPO/scripts/commerce_fulfillment_appsmith.py" \
  --output "$HOME/commerce-migration/MushroomProcess-woo-fulfillment.json"
```

Configure its separate `mushroomprocess-commerce-n8n` datasource with the same private header credential, then publish the reviewed application and activate the new workflow. Stop if the existing Ecwid page changes or the Woo endpoint is accessible without its key. Loading Woo orders should show only confirmed MP orders. The generated export leaves all existing actions/widgets intact.

## 5. Run automatic dispatch delivery and published stock

Opening stock is a reviewed exception. Normal publication uses MP free stock minus native Woo deductions that MP has not yet recorded. A hold or shipped unit represented by both systems is counted once. MP dispatch reduces physical stock and consumes its matching hold together. Product mutation and stock publication in Woo share a database mutex. Cancellation stock restoration waits for MP publication, and Woo refund restocking is disabled for managed orders. A monetary refund never asserts a physical return. Unknown stock outcomes, expired/unpaid commitments, stale snapshots and ambiguous mappings stay visible for review/retry.

Enable only this new publisher for these published IDs. Pause the older draft writer/n8n Woo writer for the same IDs. Ecwid inventory updates can remain until its checkout is paused for cutover. Put `publication_enabled: true` in the private worker config only after opening readback succeeds. Run one pass on the Linode using the existing private environment.

```bash
order publish
```

Success reports inventory `published`, the expected count, and destination delivery results. A rejected or unavailable Woo endpoint is a stop point. Validate published Woo quantities before enabling a timer. The `order` function comes from the earlier operator shell and points to the same private config.

Install the timer on the Linode only after the one-pass check. Set `ORDER_PYTHON`, `LIVE_ENV`, `LIVE_ORDER_CONFIG` to the same absolute paths used by the receiver. `LIVE_ENV` must have mode 0600 and include the established production opt-in. Run from `~/RootedOps`.

```bash
sudo tee /etc/systemd/system/dank-woo-mp-publication.service >/dev/null <<UNIT
[Unit]
Description=Publish MP dispatches and Woo availability
After=network-online.target
[Service]
Type=oneshot
User=$(id -un)
WorkingDirectory=$PWD
EnvironmentFile=$LIVE_ENV
ExecStart=$ORDER_PYTHON integrations/commerce/production_order.py publish --config $LIVE_ORDER_CONFIG
UNIT
sudo tee /etc/systemd/system/dank-woo-mp-publication.timer >/dev/null <<'UNIT'
[Unit]
Description=Retry MP commerce publication
[Timer]
OnBootSec=30
OnUnitInactiveSec=30
Unit=dank-woo-mp-publication.service
[Install]
WantedBy=timers.target
UNIT
sudo systemctl daemon-reload &&
sudo systemctl enable --now dank-woo-mp-publication.timer &&
sudo systemctl list-timers dank-woo-mp-publication.timer --no-pager
```

Success lists the next run. Stop on a failed unit. During public sales, check the last unit result and MP delivery backlog at opening, after dispatch and at close. An inventory or payment exception requires investigation and may require pausing affected products. Routine replenishment and dispatch use MP and the timer. Manual quantity edits are reserved for opening and reconciliation of exceptions.

```bash
sudo systemctl show dank-woo-mp-publication.service -p Result -p ExecMainStatus
sudo docker exec -i mushroomprocess-bridge-postgres sh -ec \
  'exec psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' <<'SQL'
SELECT target,count(*) AS pending FROM public.mp_commerce_shipment_delivery
WHERE delivered_at IS NULL GROUP BY target;
SQL
```

## 5a. Keep approved orders moving automatically

Use this after the owner acceptance has passed and ERP is in review mode. The cycle follows later updates for orders whose reviewed quote is present in a private directory. New unreviewed orders remain in the signed inbox. Tax/draft review, ERP Sales Order submission, exact Clover capture approval and posting-date approval remain explicit. The timer handles subsequent order snapshots, independent target retries, cancellation intake, dispatch delivery and stock publication.

In the private worker config, set `automation_enabled: true`, `quote_directory` to an absolute private directory, and initially `automatic_capture: false`. Keep `mode: review`, the original cutoff and all existing mappings. Use the exact same live environment and interpreter as the tested publisher.

Run on the Linode once to create the private quote directory.

```bash
cd ~/RootedOps
REVIEWED_QUOTES_DIR="$HOME/commerce-migration/reviewed-quotes"
install -d -m 700 "$REVIEWED_QUOTES_DIR"
```

Success is a private directory. Set that exact path in the private config. For each new reviewed order, use the previously prepared `ORDER_QUOTE` from the order review procedure. Admit its exact ID in ERP, then publish its quote to the timer. This replaces repeated `work-once` calls for that order.

```bash
[[ "$WOO_ORDER_ID" =~ ^[1-9][0-9]*$ ]] &&
sudo docker exec -i --user frappe erpnext-backend python3 - admit --order-id "$WOO_ORDER_ID" \
  < scripts/commerce_live_approve.py &&
install -m 600 "$ORDER_QUOTE" "$REVIEWED_QUOTES_DIR/.$WOO_ORDER_ID.pending" &&
mv "$REVIEWED_QUOTES_DIR/.$WOO_ORDER_ID.pending" "$REVIEWED_QUOTES_DIR/$WOO_ORDER_ID.json"
```

Success prints the exact ERP order admission and installs a file named with that Woo ID. Stop on any mismatch. The quote's `source_order` must be the same numeric ID as a string. Keep an approved quote stable while receipts have pending effects. Later changed amounts or destinations require review. A cancelled order's later snapshot is processed automatically with the existing reviewed context, and only unshipped MP holds/picks are released.

To automate the existing verified capture step, first approve the exact charge using the existing ERP capture helper and submit its reviewed Sales Order. Then set `automatic_capture: true` and add the exact reviewed ISO posting date under `capture_posting_dates[woo_order_id]` in the private worker config. The date remains fixed across partial failures and retries. A missing date reports `posting_date_review`, a missing approval or failed verification reports `capture_review`, and refunds report `refund_review`. The cycle never infers a posting date from the day a retry happens. Keep the manual capture command available for review.

Run one cycle on the Linode before changing the timer.

```bash
order cycle
```

Success lists only reviewed quote IDs, receipt work results and publication results. A confirmed reservation skips another capture request. Stop on an unexpected order ID, review state or inventory error. Inspect `order status --order-id "$WOO_ORDER_ID"` and the four-system ledger before proceeding.

After that pass succeeds, change the existing timer's service to the cycle. Run on the Linode from `~/RootedOps`, with the same absolute `ORDER_PYTHON` and `LIVE_ORDER_CONFIG` used earlier.

```bash
sudo mkdir -p /etc/systemd/system/dank-woo-mp-publication.service.d
sudo tee /etc/systemd/system/dank-woo-mp-publication.service.d/20-order-cycle.conf >/dev/null <<UNIT
[Service]
ExecStart=
ExecStart=$ORDER_PYTHON integrations/commerce/production_order.py cycle --config $LIVE_ORDER_CONFIG
UNIT
sudo systemctl daemon-reload &&
sudo systemctl restart dank-woo-mp-publication.timer &&
sudo systemctl start dank-woo-mp-publication.service &&
sudo systemctl show dank-woo-mp-publication.service -p Result -p ExecMainStatus
```

Success shows `Result=success` and `ExecMainStatus=0`. Stop if the unit fails. Continue comparing the Woo Orders screen with the inbox queue and resolving new orders that need approval. Remove a quote from the watched directory to pause further automated processing for that order while reviewing it. Keep the inbox, current references and quote history. A review/dead receipt still requires the existing explicit replay after fixing its cause.

To return this service to publication only, disable its timer, rename the override to `20-order-cycle.conf.disabled`, reload systemd and verify the resulting ExecStart before resuming. Keep accepted order and payment data throughout a pause or routing rollback.

## 6. Owner acceptance on shop-test

Keep public checkout restricted and confirm Woo, ERP, MP, the inbox DB, live Clover website merchant/environment and mail destination before starting. A live owner charge or postage purchase is a deliberate paid action. Use the existing Woo/Clover website integration. Use an order with two separately fulfillable units and a controlled recipient.

1. Create the new owner order after the cutoff. Confirm native signed webhook delivery returns 202 and the durable receipt is visible. Use the ongoing queue to review its mapping and tax quote, stage its MP reservation and ERP Sales Order, and verify payment capture through the existing Clover verifier. Record the Woo ID, receipt, reservation, Sales Order, submitted invoice/payment references and verified capture privately. Keep customer/address-bearing payloads out of PRs.
2. In MP's Woo fulfillment section, select the order and exact line. Enter a stable package reference. Scan one real Product or sellable whole Lot QR and Pick and pack. Check its location and hold. It remains packed and awaiting dispatch.
3. Click Open Woo order / Print shipping label. Verify the numeric ID matches and WordPress supplies the right current-host admin URL. Log in normally. Select only that package's quantities in the installed label UI. Leave mark completed and early fulfillment emails disabled. This is the explicit postage-purchase step. Record the actual service, tracking, cost and label status in MP. Reprinting or voiding must leave MP location and Woo fulfillment unchanged.
4. Confirm dispatch in MP. Verify one physical movement and one consumed unit. The timer sends the same movement to ERP and Woo. Woo remains open for the remaining unit. Verify stock has not fallen twice, including after publishing availability again.
5. Use a new package reference for the remaining unit. Prepare a second label if it will ship, or use the order's reviewed pickup/local-delivery method. Confirm only at actual handover/delivery. Verify both destination receipts, Woo completion, correct tracking, and one intended completed-order email. Use additional disposable tests for pickup/local-delivery variants when the owner order is postal.
6. Replay the same webhook and dispatch request, then retry publication. Confirm one reservation history, the same ERP financial pair, the same physical movement references and stable Woo quantities. Review any pending destination individually. An ERP timeout must leave the committed MP move and Woo acknowledgment intact.

Open public checkout only after this sequence and the ongoing review/exception procedure are accepted. A multi-order durable queue, staffed tax/financial review and automatic MP publication form the ongoing procedure. The owner pilot alone does not establish unattended accounting.

## 7. Cutover and rollback

Use [the cutover runbook](https://github.com/RayzorDuff/RootedOps/blob/feature/dank-storefront-cutover-runbook/doc/dank-woocommerce-cutover.md) for backups, HTTPS/apex routing, the saved Ecwid sitemap/42-path redirect baseline, QR samples, Google/Meta account/feed records and rollback. Preserve accepted catalog, content, theme, rates, pickup and local delivery. Recheck shipped, pickup and delivery totals, the live Clover merchant, and FluentSMTP after deployment.

At the owner-controlled switch, pause Ecwid checkout, reconcile opening commitments and change DNS/HTTPS to the existing Woo installation. Update WordPress home/siteurl, `woo_origin`, `MP_COMMERCE_WOO_ORIGIN`, webhook source/URL settings and plugin connections to the apex. Resolve a fresh generated admin order URL from Woo. Keep the same canonical logical identity and existing ERP customer links. Restart only the affected receiver/publication services after configuration changes. Keep temporary 302s until final-host, final-path and QR checks pass, then use #117's 301 switch. Verify no redirect goes through shop-test. Review Miscellaneous if a useful replacement exists. Generic dollar listings remain retired.

For rollback, restrict Woo checkout first. Preserve its accepted orders, payments, inbox, ERP documents and MP movements. Keep delivery retrying for accepted shipments while reconciling. Stop the inventory timer before restoring a prior publisher or routing stock to Ecwid. Reconcile Woo's unresolved holds/charges and physical counts before reopening Ecwid. Restore routing/canonical URLs from the saved settings without overwriting the Woo database with a pre-sale backup.

```bash
sudo systemctl disable --now dank-woo-mp-publication.timer
```

Success shows an inactive timer. Disabling the timer leaves all durable data in place. Set the private publication opt-in false for an extended pause. Restore legacy stock publishers only after confirming their inventory includes current commerce reservations.

For a refund, verify the exact Woo order/Clover capture and refunded amount, make the owner-approved refund through the supported Clover/Woo gateway interface once, record its processor reference, and reconcile ERP through review. Confirm the processor outcome before retrying a timeout. Keep physical return receipt/correction separate in MP. Do not re-add shipped units merely because money was refunded. Refund automation remains review work.

Record Google Merchant Center/Ads IDs, Ecwid data source and offer IDs, and Meta business/catalog/Pixel/shop ownership before the switch. Run a small Woo listing test against those existing assets, retaining offer IDs where the chosen connector supports them. Retire Ecwid feeds after the replacement listings, URLs and tracking pass. Account ownership/feed changes are owner actions. Keep first-payout reconciliation and confirmation of Clover Ecommerce entitlement after Ecwid cancellation on the Ecwid-retirement checklist. Actual funding/fee evidence remains RootedOps #114/#26. Clover Flex approval is outside storefront acceptance.
