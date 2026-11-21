# Dank WooCommerce switch and day-to-day operations

Continue with [the current MP fulfillment and stock acceptance runbook](commerce-fulfillment-launch.md) for the shop-test rehearsal, migrations 054–057, label preparation, dispatch and automatic published-stock operation. The earlier blocks below retain the pilot setup and host evidence.

Use this sequence with the [private setting and routing reference](https://github.com/RayzorDuff/RootedOps/blob/feature/dank-storefront-cutover-runbook/doc/dank-woocommerce-cutover.md). Run one block, check its result, then continue. Keep the same shell where a block defines variables. Store live keys, private JSON, DSNs and backups on the Linode under restricted permissions. Share only the results explicitly described below.

The production runner starts in **pilot** mode. After the owner purchase works, switch to **review** mode. In review mode the signed receiver saves new Woo orders for inspection. Each write still requires choosing an exact Woo ID and approving that order in ERP. Financial posting also requires the exact verified Clover charge. The inbox is durable. The owner works the queue. MushroomProcess (MP) owns physical stock, reservations and fulfillment. Public checkout also requires the MP fulfillment action to update the linked Woo order and MP availability to reach the published Woo listings safely.

## A. Confirm and prepare the host

### A1. Read-only host preflight

Run on the production Linode. This is the initial preflight already run on the active host.

```bash
(
  set -eu
  cd ~/RootedOps
  git log -1 --format='RootedOps %h %s'
  printf 'Modified tracked files: '
  git status --porcelain --untracked-files=no | wc -l
  for service in dank-wordpress dank-wordpress-db erpnext-backend; do
    sudo docker ps --filter "label=com.docker.compose.service=$service" \
      --format '{{.Names}} project={{.Label "com.docker.compose.project"}} {{.Status}}'
  done
  for url in https://erp.danks.store/api/method/ping https://shop-test.danks.store/my-account/; do
    curl -sS --max-time 10 -o /dev/null -w '%{http_code} %{url_effective}\n' "$url"
  done
  sudo ss -ltn 'sport = :8102'
)
```

**Pass.** Expected containers are up, both URLs show 200 and there is no unexpected listener. On the observed host, `ee24dbb` is the pre-deployment baseline and port 8102 is free. **Stop** on a missing service, dirty tracked checkout or unexplained port listener.

### A2. Read-only application and database prerequisites

Run on the Linode. This uses the environment already inside the MP container and prints no credentials.

```bash
(
  set -eu
  sudo docker exec erpnext-backend bench --site erp.danks.store list-apps
  sudo docker exec -i mushroomprocess-bridge-postgres sh -ec \
    'exec psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' <<'SQL'
SELECT current_database() AS database,
       to_regprocedure('public.mp_commerce_ingest(jsonb)') AS intake,
       to_regprocedure('public.mp_commerce_inventory()') AS availability,
       to_regprocedure('public.mp_commerce_confirm_reservation(text,text,text)') AS confirmation,
       to_regprocedure('public.mp_commerce_ship_products(text,text,text,text,jsonb)') AS shipment;
SQL
)
```

**Pass.** ERP lists `rootedops_commerce`, and MP shows the expected database. The initial Linode check returned `mushroomprocess_bridge` with intake and availability installed. Blank confirmation and shipment signatures mean the bridge is missing required functions. **Stop** before deploying. Use A2a to distinguish absent functions from a partial migration.

### A2a. Inspect the installed commerce bridge and movement prerequisites

Run on the Linode. This is read-only and uses the same database connection as A2.

```bash
(
  set -eu
  sudo docker exec -i mushroomprocess-bridge-postgres sh -ec \
    'exec psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' <<'SQL'
SELECT current_database() AS database,
       to_regclass('public.mp_commerce_payment_matches') AS payment_matches,
       to_regclass('public.mp_commerce_erp_links') AS erp_links,
       to_regclass('public.mp_commerce_shipments') AS shipments,
       to_regprocedure('public.mp_commerce_match_payment(jsonb)') AS match_payment,
       to_regprocedure('public.mp_commerce_acknowledge_products(text,text,text,text,jsonb)') AS acknowledge,
       to_regprocedure('public.mp_product_set_storage_location(bigint,bigint)') AS move_product,
       (SELECT count(*) FROM public.locations
         WHERE active AND regexp_replace(lower(name),'[^a-z0-9]','','g')='shipped')
         AS active_shipped_locations;
SQL
)
```

**Pass.** The database matches A2, payment matching and the product movement helper are present, and there is one active Shipped location. Missing ERP links, shipments and acknowledgment together are consistent with 054 still pending. **Stop** here and share the single row. Investigate any partial 054 footprint or absent prerequisite before applying either migration.

### A3. Merge and prepare the checkout

Run GitHub merges first. Merge RootedOps #117 independently and use this order for the dependency stack: #111, #112, #113, #115, #116, then the ongoing-order PR containing this file. Retarget each child after its base merges or rebase if the parent was squash-merged. MushroomProcess #115 can merge separately. RootedOps #114 is a separate settlement track.

Run the following on the Linode only after the merge audit.

```bash
cd ~/RootedOps
git switch main
git pull --ff-only
git log -1 --oneline
test -r scripts/commerce_live_approve.py && test -r doc/dank-woocommerce-linode.md
```

**Pass.** Main fast-forwards cleanly and both files exist. **Stop** if either check fails. Run the commands below from this same checkout.

### A4. Set up the shell and back up WordPress

Run on the Linode in your operator shell. Use the same `dank-store-test` project as A1. These backup commands read the live volumes and write private files.

```bash
cd ~/RootedOps
umask 077
export ERP_BACKEND=erpnext-backend
BACKUP_DIR="$HOME/commerce-migration/cutover-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$BACKUP_DIR"
dc=(sudo docker compose --env-file .env -f docker/docker-compose.dank-wordpress.yml -p dank-store-test)
wp() { "${dc[@]}" run --rm --no-deps -T dank-wordpress-cli "$@"; }

"${dc[@]}" exec -T dank-wordpress-db sh -ec \
  'MYSQL_PWD="$MARIADB_ROOT_PASSWORD" exec mariadb-dump --single-transaction -u root "$MARIADB_DATABASE"' \
  > "$BACKUP_DIR/woo.sql" &&
"${dc[@]}" exec -T dank-wordpress tar -C /var/www/html -czf - . \
  > "$BACKUP_DIR/woo-files.tar.gz" &&
test -s "$BACKUP_DIR/woo.sql" &&
tar -tzf "$BACKUP_DIR/woo-files.tar.gz" >/dev/null &&
printf 'Woo DB and files verified in %s\n' "$BACKUP_DIR"
```

**Pass.** Both backup commands and the archive check succeed. **Stop** if the final verification line is missing. Keep an encrypted off-host copy and the current DNS and routing record.

### A5. Back up ERP and MP

Run on the Linode. Set `MP_ADMIN_DSN` privately to the verified MP database. Use a PostgreSQL service/passfile to supply credentials.

```bash
sudo docker exec "$ERP_BACKEND" bench --site erp.danks.store backup --with-files &&
pg_dump --format=custom "$MP_ADMIN_DSN" > "$BACKUP_DIR/mp.dump" &&
pg_restore -l "$BACKUP_DIR/mp.dump" >/dev/null &&
sha256sum "$BACKUP_DIR/"{woo.sql,woo-files.tar.gz,mp.dump} > "$BACKUP_DIR/SHA256SUMS"
```

**Pass.** Bench reports backup files and the MP dump passes the archive check. **Stop** if a command fails or backups cannot be recovered. Keep ERP backups with the site's recovery copy.

### A6. Add the order code and MushroomProcess bridge

Run on the Linode in the deployment window, after A2a confirms the older bridge prerequisites, A5 backups are verified, and the code has merged. `MP_REPO` is the verified checkout with merged MushroomProcess #115.

```bash
./erpnext/deploy.sh erp.danks.store commerce &&
curl -fsS --max-time 10 https://erp.danks.store/api/method/ping
```

**Pass.** Commerce deploy and migration succeed and the ping returns pong. **Stop** on failure before changing any Woo routing.

Apply 054 when A2a and migration history show it is pending. If it is already installed, skip the 054 `psql -f` line after checking its full footprint.

```bash
test "$(psql "$MP_ADMIN_DSN" -X -v ON_ERROR_STOP=1 -Atc 'SELECT current_database()')" = mushroomprocess_bridge &&
test -r "$MP_REPO/schema/pgsql/054_commerce_operational_bridge.sql" &&
test -r "$MP_REPO/schema/pgsql/055_commerce_atomic_shipment.sql" &&
psql "$MP_ADMIN_DSN" -X -v ON_ERROR_STOP=1 \
  -f "$MP_REPO/schema/pgsql/054_commerce_operational_bridge.sql" &&
psql "$MP_ADMIN_DSN" -X -v ON_ERROR_STOP=1 \
  -f "$MP_REPO/schema/pgsql/055_commerce_atomic_shipment.sql" &&
psql "$MP_ADMIN_DSN" -X -v ON_ERROR_STOP=1 -c "
  SELECT to_regprocedure('public.mp_commerce_confirm_reservation(text,text,text)') AS confirmation,
         to_regprocedure('public.mp_commerce_ship_products(text,text,text,text,jsonb)') AS shipment"
```

**Pass.** Both signatures are present. Verify execution grants for the configured worker and fulfillment roles using the same role connections. **Stop** on a database, migration or grant mismatch. Keep Ecwid accepting sales until the cutover window.

## B. Switch with checkout restricted and complete the pilot

### B1. Set the protected route and stop competing sales

Use Ecwid admin and the Linode. At the cutover window, put Ecwid in storefront maintenance mode and verify direct Ecwid checkout is closed. Pause stock writers and any POS sales against stock pools reserved for Woo. Configure the owner-only apex TLS vhost and the exact signed Woo webhook proxy from the routing reference. Inside the apex server block, use `include /etc/nginx/dank-woo/checkout-active.conf;`. Prepare `checkout-closed.conf` in that directory with the reviewed owner IP allowlist and `deny all;`. Prepare `checkout-open.conf` with a comment only. Keep the webhook location's own access controls and signature verification. Validate the owner and a separate client. Existing sandbox/test Woo order history stays in the same DB.

```bash
sudo ln -sfn /etc/nginx/dank-woo/checkout-closed.conf \
  /etc/nginx/dank-woo/checkout-active.conf &&
sudo nginx -t && sudo systemctl reload nginx
```

**Pass.** NGINX validates and reloads. The owner can reach Woo while an unauthorised client cannot buy, including through order-pay or the old test hostname. **Stop** before changing DNS if the gate is ineffective, another channel can sell those units, or the old routing cannot be restored.

### B2. Change the Woo URL and check opening stock

Run on the Linode. You perform the DNS switch. Install the #117 theme build using the routing reference. Update the existing WordPress database's canonical URLs and keep the legacy redirects temporary.

```bash
wp option update home https://danks.store &&
wp option update siteurl https://danks.store &&
wp option update rootedops_ecwid_redirect_permanent 0 &&
wp option get home &&
wp option get siteurl
```

**Pass.** Both URLs show the apex. **Stop** if you reach the old store unexpectedly, the certificate is wrong or the checkout gate fails. Review menu, media and webhook URLs before broad edits.

Run this read-only export on the Linode, then populate the private opening CSV from the reviewed launch list. In Woo, enable managed stock and disable backorders. Use one positive allocation per physical MP pool.

```bash
psql "$MP_ADMIN_DSN" -X --csv -v ON_ERROR_STOP=1 -c "
 SELECT c.ecommerce_id AS mp_id, c.external_product_id, c.external_variation_id,
        c.external_sku AS sku, c.erp_item_code,
        c.item_id::text || ':' || coalesce(c.strain_id::text,'none') AS pool_key,
        i.available_quantity AS mp_available
 FROM mp_ecommerce_catalog_inventory() c
 JOIN mp_commerce_inventory() i USING (ecommerce_id)
 WHERE c.provider='woocommerce' AND c.site_key='danks.store'
 ORDER BY c.ecommerce_id
" > "$BACKUP_DIR/mp-opening.csv"
```

**Pass.** The export contains each expected launch SKU and quantity, including zero allocations. **Stop** if empty, incomplete or ambiguous. Build `OPENING_CSV` with the header `woo_id,parent_woo_id,mp_id,sku,source_key,pool_key,mp_available` and the reviewed Woo ownership keys. Apply the approved quantities in Woo's Inventory UI while checkout is closed.

```bash
python scripts/commerce_cutover_check.py stock "$OPENING_CSV" --host danks.store
```

**Pass.** Every reviewed, published listing returns `ok`. **Stop** for missing or extra launch listings, stock differences, ambiguous pool/SKU mappings, outstanding Ecwid commitments, or missing credentials. Check the shipped, pickup and local-delivery carts and mail before the purchase. Run the apex redirect and current printed QR checks with the reviewed manifests.

### B3. Prepare signed pilot intake

Run on the Linode. Set up the private worker and ERP config using section 6 of the routing reference. Supply the single new pilot order ID, cutoff, exact Item mappings, reviewed tax quote and dedicated inbox DB. Set the environment variables privately in the worker shell. The Woo sender needs a reachable HTTPS endpoint and the configured signature secret.

```bash
cd ~/RootedOps
export COMMERCE_PRODUCTION_ORDER_PILOT=1
order() { python integrations/commerce/production_order.py "$@" --config "$LIVE_ORDER_CONFIG"; }
order init &&
sudo docker exec "$ERP_BACKEND" bench --site erp.danks.store set-config \
  --parse commerce_order_integration_enabled True
```

**Pass.** Both commands succeed. **Stop** on a missing DB/credential/quote, server flags disagreement or unexpected ingress.

Run this next block on the Linode only after preparing the mode-0600 `LIVE_ENV` systemd environment file containing the private worker settings. Set `ORDER_PYTHON` to the absolute interpreter path from the same Python environment you used for initialization. Use simple absolute paths without spaces.

```bash
test -x "$ORDER_PYTHON" && test -r "$LIVE_ENV" &&
sudo tee /etc/systemd/system/dank-woo-order-inbox.service >/dev/null <<UNIT
[Unit]
Description=Dank Woo signed order inbox
After=network-online.target docker.service
Wants=network-online.target

[Service]
User=$(id -un)
WorkingDirectory=$PWD
EnvironmentFile=$LIVE_ENV
ExecStart=$ORDER_PYTHON integrations/commerce/production_order.py serve --port 8102 --config $LIVE_ORDER_CONFIG
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT
```

**Pass.** Unit write succeeds. **Stop** if an existing listener or service was not accounted for. Start the reviewed unit:

```bash
sudo systemctl daemon-reload &&
sudo systemctl enable --now dank-woo-order-inbox.service &&
sudo systemctl is-active dank-woo-order-inbox.service &&
sudo ss -ltn 'sport = :8102'
```

**Pass.** The service is active and the listener is loopback on port 8102. Test unsigned ingress from the reviewed sender and expect 400. Enable only the signed Woo created/updated hooks and save the pilot order to trigger delivery. **Stop** if the worker exits, TLS or signature check fails, or the expected order receipt is missing.

### B4. Exercise one order

Run on the Linode in the worker operator shell. You handle the actual purchase. Review each command's result before running the next step. The runbook reference has the exact pilot approval, charge settings and shipment command.

```bash
order status
order work-once
order status
order ledger
```

**Pass.** The approved order has one ERP sales order and the expected MP hold. **Stop** when the inbox reports a dead letter, pending retry, mismatched total or unexpected stock. Review the ERP Sales Order, then make the approved purchase with checkout still restricted. After the signed paid update is staged and the exact live charge is approved in both configs:

```bash
order work-once
order status
order capture --posting-date "$REVIEWED_POSTING_DATE"
order ledger
```

**Pass.** The one verified charge produces one ERP invoice/receipt pair and a confirmed MP reservation. Repeat the same verified command to confirm replay behavior. **Stop** for a failed capture, incorrect financial references, or an unreviewed refund. For an engineering-only smoke test, use the explicit MP movement and ERP acknowledgment block in the routing reference. Confirm ERP receipt replay preserves one document. Public checkout also requires the actual MushroomProcess fulfillment action and Woo projections in D.

## C. Accept public orders with a durable review queue

### C1. Switch to review mode while checkout is restricted

In the Linode operator shell with the same checkout, ERP name, cutoff and dedicated inbox. Save a private copy of the pilot settings. Move ERP to review mode first. This carries forward the pilot order and its exact payment approval. Other ERP writes still require per-order approval.

```bash
sudo docker exec -i --user frappe "$ERP_BACKEND" python3 - review \
  < scripts/commerce_live_approve.py
```

**Pass.** Prints `ERP review applied`. **Stop** if it fails. In the existing private worker JSON, set `"mode": "review"` without changing the cutoff, DBs, mappings or quote policy. Restart the supervised receiver so it reads the new config. Verify the webhook and queue, and confirm the pilot is still visible.

```bash
sudo systemctl restart dank-woo-order-inbox.service &&
sudo systemctl is-active dank-woo-order-inbox.service &&
order queue
order ledger --order-id "$PILOT_WOO_ORDER_ID"
```

**Pass.** Queue displays order IDs/counts and the pilot's ledger keeps its original references. **Stop** if signed intake is unhealthy or you cannot staff the queue during the sales window. Keep checkout restricted until known checkout paths, mappings, stock, and the entire owner pilot are accepted, and the MP-to-Woo checks in D pass. Open only the Woo sales window. Keep Ecwid in maintenance. Run the next block on the Linode only after those checks pass.

```bash
sudo ln -sfn /etc/nginx/dank-woo/checkout-open.conf \
  /etc/nginx/dank-woo/checkout-active.conf &&
sudo nginx -t && sudo systemctl reload nginx
```

**Pass.** The outside customer path is available with the reviewed products and checkout methods. **Stop** on a routing, listener or stock mismatch and run the close block below.

### C2. Inspect the queue and select one paid or payable order

Run on the Linode at opening, on every new-order notice, before fulfillment, and before leaving the store unattended. Cross-check Woo Admin **WooCommerce → Orders** so an order with a missing webhook or a failed notice cannot go unnoticed. The inbox report reflects delivery, not payment or physical fulfillment.

```bash
order queue
read -r -p 'Woo numeric order ID: ' WOO_ORDER_ID
order review --order-id "$WOO_ORDER_ID"
order status --order-id "$WOO_ORDER_ID"
order ledger --order-id "$WOO_ORDER_ID"
```

**Pass.** All three views show the same reviewed order, states and totals. The review command omits contact details and raw bodies. An initial MP status of `missing` is normal. **Stop** for a missing receipt, a same-second conflict, an order edit in dispute or an unknown SKU. Pause public checkout if orders are arriving faster than you can clear or independently account for them. For a missing webhook, verify Woo delivery logs and use a fresh signed resend/native update. Keep the order visible in Woo until it is accounted for.

### C3. Stage the selected order

Use the reviewed worksheet values and Woo checkout view to obtain the matching order-specific tax quote using your approved tax policy. The quote includes the selected ID, destination hash, approved lines and amounts. A zero-tax quote still requires the reviewed determination. `ORDER_QUOTE` points to that mode-0600 JSON file. The worker also accepts the existing per-order quote map in its private config. A quote mismatch or missing tax procedure is a public-opening blocker for the affected checkout routes.

```bash
sudo docker exec -i --user frappe "$ERP_BACKEND" python3 - admit --order-id "$WOO_ORDER_ID" \
  < scripts/commerce_live_approve.py &&
order work-once --order-id "$WOO_ORDER_ID" --tax-quote "$ORDER_QUOTE"
```

**Pass.** ERP admits this ID and the worker reports `worked: true`. The command processes at most one receipt. Run the next block after each receipt. Use the same approved quote for matching money on subsequent receipts.

```bash
order status --order-id "$WOO_ORDER_ID"
order ledger --order-id "$WOO_ORDER_ID"
```

**Pass.** The newest receipt is `done` with expected ERP/MP references, no unresolved earlier review, and one expected hold. If there are further pending receipts, repeat `work-once` for this ID. **Stop** on a dead letter, conflicting revisions, a missing ERP reference, or incorrect quantity. A rejected ERP preflight leaves the receipt uncompiled and creates no hold. Correct the review and retry; requeue a dead letter only after correcting the cause:

```bash
order replay --order-id "$WOO_ORDER_ID" --event-id "$REVIEWED_EVENT_ID"
```

**Pass.** Only that receipt is requeued. **Stop** if its identity differs or there are already effects that need reconciliation. A cancelled/failed order with no sale, or a refund with posted effects, needs individual review against Woo, Clover, ERP and MP. Keep any remaining hold until reconciled.

### C4. Verify and account for a paid order

Run after the paid receipt completed and the reviewed ERP Sales Order was submitted. Use the verified charge ID and approved posting date from the private operator review. Treat `CLOVER_CHARGE_ID` as private transaction data when sharing output.

```bash
sudo docker exec -i --user frappe "$ERP_BACKEND" python3 - capture \
  --order-id "$WOO_ORDER_ID" --charge-id "$CLOVER_CHARGE_ID" \
  < scripts/commerce_live_approve.py &&
order capture --order-id "$WOO_ORDER_ID" --charge-id "$CLOVER_CHARGE_ID" \
  --posting-date "$REVIEWED_POSTING_DATE" &&
order ledger --order-id "$WOO_ORDER_ID"
```

**Pass.** The invoice/receipt are linked and MP confirms the hold for the order. Check the amount and reference once. **Stop** on a capture that is unverified, refunded, mismatched or missing. Follow the refund/rollback reference as needed. Ship only against the confirmed MP reservation. The following command exercises the existing ERP projection for a movement already committed by MP:

```bash
order shipment --order-id "$WOO_ORDER_ID" --movement-reference "$MOVEMENT_REFERENCE"
order ledger --order-id "$WOO_ORDER_ID"
```

**Pass.** The committed movement has an ERP acknowledgment and the shipped quantity matches. **Stop** on a missing movement, quantity mismatch, or unconfirmed capture. Retry an ERP timeout using the same reference.

## D. Verify MushroomProcess fulfillment and Woo stock before public checkout

Use the [current fulfillment acceptance sequence](commerce-fulfillment-launch.md). It supplies the Product/whole-Lot packing UI, label handoff, atomic MP dispatch and independent ERP/Woo publication. Verify native and hosted acceptance before opening public checkout. Routine replenishment and fulfillment use MP and its publisher. Opening inventory and unexplained differences still require reconciliation.

To close Woo checkout for a stock count or an incident, run on the Linode:

```bash
sudo ln -sfn /etc/nginx/dank-woo/checkout-closed.conf \
  /etc/nginx/dank-woo/checkout-active.conf &&
sudo nginx -t && sudo systemctl reload nginx
```

**Pass.** An external client cannot check out. **Stop** if checkout remains reachable. Keep the signed inbox running while you reconcile orders already accepted. Reopen using C1 only after verifying counts and payment states.

Run the visual shipped/pickup/delivery checks before exposing those methods. Retire Ecwid only after first-payout reconciliation and confirmation that Clover Ecommerce entitlement survives Ecwid cancellation. The routing reference includes refund and feed rollback. For a full integration pause after checkout is closed, use:

```bash
sudo docker exec "$ERP_BACKEND" bench --site erp.danks.store set-config \
  --parse commerce_order_integration_enabled False
```

**Pass.** ERP order mutations are disabled. Preserve the worker config, queue, Woo payments and MP/ERP records. **Stop** before reopening Ecwid if Woo can still accept orders or unresolved Woo holds would be double-sold.
