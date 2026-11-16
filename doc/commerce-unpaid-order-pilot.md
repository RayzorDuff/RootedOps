# Automatic WooCommerce unpaid-order pilot

WooCommerce emits standard `order.created` and `order.updated` webhooks.
The receiver verifies the raw-body HMAC and commits the receipt before HTTP 202.
The Woo store and numeric order ID identify the order. The exact raw SHA-256
identifies a receipt, and stable Woo line IDs identify reservations. MushroomProcess
and ERP record their outcomes separately. This pilot creates draft Sales Orders
and unconfirmed holds. It has no payment or physical fulfillment step.

The reviewed pilot accepts only synthetic Items and order-specific ERP draft
approvals. It compares Woo product ID, variation ID and exact SKU to the reviewed
map and MushroomProcess's enabled channel catalog, then checks per-Item amounts
and the ERP-calculated order total. This fixture requires zero discounts, fees,
shipping and tax. Confirm any future tax-bearing case against native ERP tax
configuration before expanding the pilot. Registered buyers resolve through
Commerce Customer Link; a guest requires the reviewed ERP Customer. Checkout
addresses stay in the private Woo order and its raw inbox receipt. They are omitted
from application payloads and account profile changes. Restrict access to the
disposable inbox and retire its raw synthetic data under the operator's test-data
cleanup procedure.

## Confirm the staging targets

`shop-test.danks.store` shares the active Linode with production. The working
customer pilot uses `erp.danks.store`. Use a separate bench and database for
`erp-test.danks.store` to run this order pilot. Keep the customer webhook and
worker, Ecwid, production order flags and live merchant configuration in service
as they are. Coordinate with the storefront rebuild owner before opening a
fixture-only order window. The native Woo topics cover all orders in their shop.

From the staging ERP bench and the order worker's shell, respectively, run:

```bash
bench --site erp-test.danks.store list-apps
psql "$MP_TEST_DSN" -X -Atc "SELECT current_database(), to_regprocedure('public.mp_commerce_ingest(jsonb)'), to_regprocedure('public.mp_commerce_link_erp(jsonb)')"
psql "$COMMERCE_INBOX_DSN" -X -Atc 'SELECT current_database()'
sudo ss -ltnp 'sport = :8101'
```

Expect `rootedops_commerce`, the two installed MP functions, separately
provisioned disposable inbox and MP databases, and an unused port 8101.
The runtime accepts local test DSNs with database names `commerce_test`,
`commerce_integration_test`, or `mushroomprocess_test`. Review the databases
and mail routing independently of their names. Confirm that the Woo fixture
and ERP email end up in a staging sink, the fixture can use an unpaid/manual
gateway, and the worker can reach the authenticated staging ERP method over TLS.
If any target is missing, use the disposable native fixture instead of activating
the live pilot. [Customer staging inventory](commerce-customer-sync.md#batch-1-read-only-preflight-on-the-shared-linode)

On the **dedicated staging bench** with this branch deployed, enable the ERP order
service with `bench --site erp-test.danks.store set-config --parse commerce_order_integration_enabled True`.
Use a staging System Manager or Sales Manager API credential. Stage a dedicated
synthetic Item, an explicit guest Customer, and a synthetic sellable unit with
an enabled MushroomProcess ecommerce row. Its provider, site, external SKU,
external product/variation IDs and ERP Item code must match. For a registered
case, create a synthetic Woo account and an explicit Commerce Customer Link in
the staging ERP. The Order worker does not use the production customer pilot.

## Start the receiver

Save a mode-0600 JSON file and set `ORDER_INBOX_CONFIG` to its path. Replace the
example IDs and review the exact synthetic gateway. An empty key is Woo's
manual admin-order gateway value. Keep the draft map empty until the first
synthetic Woo order ID is known.

```json
{
  "erp_base_url": "https://erp-test.danks.store",
  "sites": {
    "shop-test.danks.store": {
      "unpaid_pilot": true,
      "secret_envs": ["WOO_ORDER_WEBHOOK_SECRET"],
      "synthetic_item_codes": ["ERP-SYN-ORDER"],
      "mappings": {
        "501": {"product_id": 501, "sku": "SYN-ORDER", "ecommerce_id": 123, "erp_item_code": "ERP-SYN-ORDER"}
      },
      "gateways": {"": "manual_unpaid"}
    }
  },
  "approved_erp_drafts": {}
}
```

Set `WOO_ORDER_WEBHOOK_SECRET` to a private random secret of at least 32 characters.
Use a secret separate from customer sync. Set `ERP_AUTHORIZATION` privately and
install `psycopg[binary]==3.3.6` in the isolated worker environment. Start the
listener from the branch checkout with both dedicated test DSNs set:

```bash
export COMMERCE_STAGING_ONLY=1
python integrations/commerce/runtime.py init
python integrations/commerce/runtime.py serve --config "$ORDER_INBOX_CONFIG" --port 8101
```

In the existing **shop-test TLS server block**, add this exact location. Verify
the selected shop host reaches the HTTPS receiver directly. If Woo has an
outbound guard, permit only this URL. Review NGINX and reload with
`sudo nginx -t && sudo systemctl reload nginx` during the coordinated window.

```nginx
location = /webhooks/woocommerce/shop-test.danks.store {
    limit_except POST { deny all; }
    proxy_pass http://127.0.0.1:8101;
    proxy_set_header X-WC-Webhook-Signature $http_x_wc_webhook_signature;
}
```

In **WooCommerce → Settings → Advanced → Webhooks**, create two active webhooks,
one for **Order created** and one for **Order updated**. Use the same
`https://shop-test.danks.store/webhooks/woocommerce/shop-test.danks.store` delivery
URL, the pilot secret, and the v3 Woo REST payload. If the UI sends an unsigned
setup ping, HTTP 400 is expected. If the UI did not persist the entries, use the
following fallback from the verified staging WP-CLI. Set `WOO_PILOT_ADMIN_ID` to
the staging Woo administrator's numeric ID and export the existing secret into
the WP-CLI process. If using Compose `run`, pass `-e WOO_ORDER_WEBHOOK_SECRET`
before the CLI service name.

```bash
wp --url=https://shop-test.danks.store --user="$WOO_PILOT_ADMIN_ID" eval '
$site = "https://shop-test.danks.store";
$secret = getenv("WOO_ORDER_WEBHOOK_SECRET");
if (untrailingslashit(get_option("home")) !== $site ||
    !current_user_can("manage_woocommerce") || strlen((string) $secret) < 32) {
    throw new RuntimeException("Verify staging site, role and private secret.");
}
$url = $site . "/webhooks/woocommerce/shop-test.danks.store";
$store = WC_Data_Store::load("webhook");
foreach (["order.created", "order.updated"] as $topic) {
    $matches = [];
    foreach ($store->get_webhooks_ids() as $id) {
        $existing = wc_get_webhook($id);
        if ($existing && $existing->get_topic() === $topic &&
            $existing->get_delivery_url() === $url) {
            $matches[] = $existing;
        }
    }
    if (count($matches) > 1) {
        throw new RuntimeException("Review duplicate pilot webhooks before enabling.");
    }
    $hook = $matches[0] ?? new WC_Webhook();
    $hook->set_name("Staging unpaid pilot " . $topic);
    $hook->set_user_id(get_current_user_id());
    $hook->set_topic($topic);
    $hook->set_api_version("wp_api_v3");
    $hook->set_delivery_url($url);
    $hook->set_secret($secret);
    $hook->set_status("active");
    $hook->save();
    printf("%s webhook id: %d\n", $topic, $hook->get_id());
}'
```

Expect one ID for each topic. If WP cron is disabled, run the queued deliveries
with `wp action-scheduler run --hooks=woocommerce_deliver_webhook_async` from the
verified staging WP-CLI after each Woo save.

## Run the fixture

1. In Woo **Orders → Add order**, create one **Pending payment** guest order
   with a fictitious billing address and the mapped synthetic product. Set one
   unit and the reviewed fixture price. Leave the transaction ID, tax, shipping,
   fees and discounts empty. Save and run the Woo queue if needed. Expect
   HTTP 202 with `duplicate: false` and a pending durable receipt.
2. In the private JSON, add `woocommerce|shop-test.danks.store|WOO_ORDER_ID` to
   `approved_erp_drafts`. Use the actual synthetic numeric order ID and reviewed
   ERP values, for example:

   ```json
   {
     "customer": "SYN-GUEST-CUSTOMER",
     "company": "Synthetic Staging Company",
     "currency": "USD",
     "conversion_rate": 1,
     "transaction_date": "2026-11-15",
     "delivery_date": "2026-11-15",
     "selling_price_list": "Synthetic USD",
     "items": [{"item_code": "ERP-SYN-ORDER", "qty": 1, "rate": "12.00", "delivery_date": "2026-11-15"}],
     "taxes": [],
     "docstatus": 0,
     "ignore_pricing_rule": 1
   }
   ```

   Use current reviewed dates for the fixture. For the registered case, omit
   `customer` so ERP resolves the staging link, or specify its exact Customer.
   In another shell with the same staging env and `WOO_ORDER_ID` set, run:

   ```bash
   python integrations/commerce/runtime.py work-once --config "$ORDER_INBOX_CONFIG" \
     --order-site shop-test.danks.store
   python integrations/commerce/runtime.py order-status \
     --order-key woocommerce shop-test.danks.store "$WOO_ORDER_ID"
   ```

   Expect a `done` receipt with MushroomProcess status `applied` and an ERP
   `sales_order` reference with `accounting_posted: false`. Confirm one draft
   Sales Order, no Sales Invoice or Payment Entry, and one held unit in MP.
   Record the order ID, receipt, ERP draft and MP order key. Use the command below
   to view only these synthetic MP references:

   ```bash
   psql "$MP_TEST_DSN" -X -v order_id="$WOO_ORDER_ID" <<'SQL'
   SELECT o.external_order_id, o.status, l.sales_order,
          coalesce((SELECT sum(r.quantity) FROM mp_commerce_reservations r
                    WHERE (r.provider,r.site_key,r.external_order_id) =
                          (o.provider,o.site_key,o.external_order_id)),0) AS held
     FROM mp_commerce_orders o JOIN mp_commerce_erp_links l
       USING (provider,site_key,external_order_id)
    WHERE o.provider='woocommerce' AND o.site_key='shop-test.danks.store'
      AND o.external_order_id=:'order_id';
   SQL
   ```

3. Replay a byte-identical **synthetic** receipt through the staging HTTPS
   endpoint. Set `ORDER_RECEIPT_ID` to the inbox receipt, and run the following
   with the private secret still in the environment. It reads the raw bytes
   directly from the disposable inbox and sends them without displaying them.

   ```bash
   export ORDER_RECEIPT_ID WOO_ORDER_ID
   PYTHONPATH=integrations/commerce python - <<'PY'
   import base64
   import hmac
   import json
   import os
   from urllib.request import Request, urlopen
   from runtime import connect_test

   site = 'shop-test.danks.store'
   db_connect = connect_test(os.environ['COMMERCE_INBOX_DSN'])
   with db_connect() as db:
       raw, = db.execute("""
           SELECT raw_body FROM commerce_inbox
           WHERE provider='woocommerce' AND site_key=%s AND external_order_id=%s AND event_id=%s
       """, (site, os.environ['WOO_ORDER_ID'], os.environ['ORDER_RECEIPT_ID'])).fetchone()
   signature = base64.b64encode(hmac.digest(os.environ['WOO_ORDER_WEBHOOK_SECRET'].encode(), raw, 'sha256')).decode()
   url = 'https://' + site + '/webhooks/woocommerce/' + site
   with urlopen(Request(url, data=raw, headers={'Content-Type': 'application/json',
                                                'X-WC-Webhook-Signature': signature}), timeout=10) as response:
       print(response.status, json.load(response))
   PY
   ```

   Expect HTTP 202, `duplicate: true` and the identical receipt ID. Verify the
   reservation and ERP draft counts are unchanged.

4. Once the first receipt is done, change the same Woo order to **Cancelled**
   and save. Allow at least one source-clock second between distinct saves.
   Run the Woo queue if needed, then the worker and status commands. Expect the
   same order and ERP draft, MP status `cancelled`, and held units `0`. Repeat
   with the linked registered customer and verify the draft's Customer and
   untouched account addresses.

An earlier order receipt awaiting retry blocks a later receipt for that order.
The worker retains a successful MP receipt and retries the ERP leg independently.
Superseded snapshots skip ERP. Distinct changes with the same Woo GMT second
are quarantined as `revision_conflict`; Woo's delivery time cannot establish
source order. Review Woo's current order and existing receipts, then use a
legitimate later Woo save for the confirmed state. Exact duplicate receipt and
stale snapshot paths are separate. An unmapped/disabled or conflicting mapping
has a stable review code. After correcting configuration for an unmaterialized
receipt, requeue the same receipt with:

```bash
python integrations/commerce/runtime.py replay \
  --event-key woocommerce shop-test.danks.store "$ORDER_RECEIPT_ID"
```

If an event already reached a target, reconcile the target before changing any
identity or financial data. Pause both pilot Woo webhooks, stop the dedicated
listener and worker, and remove the exact NGINX location with a validated reload
to disable the route. Set the dedicated staging ERP flag back to false via
`bench --site erp-test.danks.store set-config --parse commerce_order_integration_enabled False`.
Reconcile or cancel any remaining synthetic reservations before cleanup.

## Evidence boundary

- Earlier hosted test2 Woo order #51 used operator-relayed delivery into native
  MushroomProcess and ERP. [Installed evidence](commerce-operational-test2.md)
- A local run of all nine native inbox tests passed with WordPress 7.1.4,
  WooCommerce 11.2.1, MariaDB 11.8, PostgreSQL 18 and MushroomProcess main.
  Woo order `11` sent signed `order.created` and `order.updated` webhooks via
  Action Scheduler. The receiver acknowledged both with HTTP 202. Exact replay
  kept the receipt and the hold count. The invalid signature returned 400.
  The one held unit went to zero on cancellation. The native MP order key was
  `woocommerce|shop-test.danks.store|11`. The synthetic creation receipt was
  `8fbebbc81c3b893088383b879ec6d60cd63b844e11f1ba88fb4cf752a13caa0b`, and
  the cancellation receipt was
  `051560bb04d7401e5f53021d61d85c4461785666c1df50a7d12aaaca8f442137`.
  ERP transport used a fixture response, `SYNTHETIC-WOO-SO`.
- The separate GitHub Frappe job uses native Sales Order drafts and tests guest
  and registered resolution. The inbox job repeats automatic Woo delivery
  using a disposable PostgreSQL 16 database.
- Hosted automatic acceptance still requires the isolated destinations above.
  Capture Woo order ID, inbox receipt, MP order key and Sales Order ID privately.
- Deterministic ERP draft mapping, native destination tax, verified Clover capture
  and ERP invoice/receipt reconciliation, and MP-to-ERP shipment acknowledgement
  are later milestones.

## Reviewed mapping follow-up

Specify `sites["shop-test.danks.store"].draft_policy` in the private order
config instead of scheduling an order-specific approval. It takes
`company`, `currency`, `selling_price_list`, `guest_customer`, an optional
`shipping_item` for the reviewed nonstock ERP shipping line, and `tax_quotes`.
Registered customers resolve by the existing Woo customer link in staging
ERPNext. Keep the original exact Woo/MP item mapping and synthetic allowlist.
Add the same shipping Item in ERP site config as `commerce_order_shipping_item`.
Leave `allow_zero_tax_fixture` and the ERP setting
`commerce_mapped_zero_tax_fixture` false except for disposable zero-tax fixtures.

The compiler uses Woo line totals after allocated discounts, adds the separate
shipping Item and verifies the gross sum. If the exact line amount cannot be
represented as a cent-denominated unit rate, it goes to commercial review.
Tax requires a reviewed quote keyed by order ID, with the current order's
destination fingerprint in `location_ref` and exact tax amount. The fingerprint
is the SHA-256 of the JSON array of trimmed, uppercase shipping
`country,state,postcode,city` (billing is used when shipping country is absent).
ERP validates the existing jurisdiction, tax class and liability-account
contract and independently checks its calculated total. The implementation does
not infer tax from checkout or turn on production posting.

Hosted preflight for the active Linode:

```bash
curl -fsS --max-time 10 https://erp-test.danks.store/api/method/ping
sudo docker ps --filter label=com.docker.compose.service=erpnext-backend \
  --format '{{.Names}} {{.Ports}}'
sudo ss -ltnp 'sport = :8101'
```

Observed from this work session: Woo My Account returned 200 and the ERP route
returned 503 with an upstream connection failure. A dedicated ERP bench must
answer the site ping with `{"message":"pong"}` from the worker location.
Image/web server reachability requires host diagnostics; an ERP role credential
cannot resolve a disconnected upstream. Compare the staging NGINX
`proxy_pass` target with the listening staging service, verify
`bench --site erp-test.danks.store list-apps` inside that dedicated backend,
then complete the database and mail-sink checks above. Do not point the order
worker at the production ERP site used by the customer pilot.
