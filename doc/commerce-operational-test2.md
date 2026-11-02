# Operational readiness: installed test2 evidence, 2026-11-02

Baseline: RootedOps main `0654c4c4c6efe8d1ae030657ab925fbbd8b65e97` (merged
#54); MushroomProcess main `451393c621b64c5bd4ca7d03b1525c6253f641ae`.
This session advances native tax and operational integration. It does not expand
the 22-product catalog checkpoint or rerun the broad native integration suites.

## Installed ERPNext tax configuration

ERPNext 16.13.0 / Frappe 16.14.0, rootedops_commerce 0.3.1. The native fixture in
[tax architecture](commerce-tax-architecture.md) is installed and repeat-stable:

- Tax Category: `TEST2 CO JOHNSTOWN COMPONENTS ONLY`.
- Sales Taxes and Charges Template: same title with ` - DML` suffix, non-default.
- Tax Rule: `ACC-TAX-RULE-2026-00001`, scoped exclusively to that category,
  shopping-cart use off.
- Accounts: `TEST2 CO State Tax Components - DML` and
  `TEST2 CO Johnstown Tax Components - DML`, under DML Duties and Taxes.
- Grocery and merchandise Item Tax Templates; `TEST2-TAX-GROCERY` and
  `TEST2-TAX-MERCH`, both synthetic non-stock Items.
- Synthetic Customer: `RootedOps Tax Acceptance Fixture`.

Native unsaved Sales Invoice calculations passed: $100 grocery → $3.50;
$100 merchandise → $6.40; mixed $200 → $9.90 **component subtotals only**.
County/district components and complete address-based quotations are unvalidated.
No invoice was saved or submitted by this fixture; no real catalog Item was
classified. Woo tax calculation remains `no`.

## Installed unpaid order lifecycle

Actual WooCommerce REST order data, actual PostgreSQL functions and actual native
ERP documents were used. Delivery was **operator-relayed**: the runner signs the
retrieved Woo snapshot, uses the existing authenticated durable Inbox and
PostgresInventory adapters, then the ReviewedERP adapter calls the installed
native `order_service.stage_order`. This is not evidence that Woo emits/delivers
its webhook automatically, that a live HTTP reverse proxy works, or that n8n
routes it. Existing network/mail/cron/payment isolation was retained.

| Identity / value | Installed result |
| --- | --- |
| Woo numeric order ID | `51` |
| Woo customer ID | `2`, synthetic `.invalid` email; repeat lookup returns same ID |
| Woo product ID / SKU | `50` / `TEST2-TAX-MERCH`, draft/hidden, stock 0 |
| Commercial line | Quantity 1 × USD $12.00 |
| Tax total | $0.00 with tax calculation disabled; not destination-tax acceptance |
| MP database | New `commerce_integration_test` inside existing MP PostgreSQL container |
| MP ecommerce mapping | `1`, exact Woo ID/SKU → same ERP Item |
| ERP Sales Order | `SAL-ORD-2026-00001`, draft |
| ERP customer | Same synthetic tax acceptance Customer, explicit reviewed crosswalk to Woo customer 2 |
| ERP external order key | `569f6d3cd13da32d576745bf6c0d09dc6f40167be1e1221dd8c973e06757a8b8` |
| ERP source namespace | `woocommerce` / `shop-test2.danks.store` / `51` |
| Initial reservation | 1 unit, one order and one ERP link |
| Duplicate raw receipt | Rejected as duplicate; no second delivery/reservation/order |
| Invalid signature | Rejected before durable receipt |
| Repeated native ERP staging | Same Sales Order/reference, no duplicate |
| Unpaid reservation confirmation | Rejected: no verified payment match |
| Unpaid shipment acknowledgment | Rejected: confirmed active reservation required; no stock movement |
| Cancellation | Same Woo/MP/ERP order identities, MP reserved quantity 0 |
| Final inbox | Two completed events (pending, cancelled), one order and one ERP link |
| Financials | No Clover transaction, Sales Invoice or Payment Entry |

The restored `mushroomprocess_bridge` database initially had no `mp_commerce*`
functions. Its data/schema were not migrated or reset. A new database received
the existing upstream schema migrations (including their reference seeds), inbox
DDL and two isolated synthetic stock units. No schema/data were copied from the
restored database. An ephemeral runner reuses the installed ERP image's psycopg2
through a small DB-API shim; it joins the MP container's network namespace and
publishes no ports. No shared service dependency or network configuration changed.

### Installed defect corrected

WooCommerce 11.2.1's customer REST controller filters protected user metadata
(`is_protected_meta`). The existing customer adapter's underscore-prefixed
identity/hash keys were silently discarded on creation. It now uses supported
`rootedops_source_key` / `rootedops_customer_hash`, verifies persistence by readback,
and accepts consistent legacy keys where present. Unowned/changed emails and
conflicting identities still fail closed. The one synthetic customer created
before this fix was explicitly reconciled after checking its exact deterministic
username, email and absence of conflicting keys; no general adoption path exists.
Three targeted regression tests pass. Actual installed customer 2 replays stably.

### Remaining installed order gates

No verified Clover sandbox capture exists. Consequently paid fulfillment,
submitted invoice/payment linking, successful partial shipment acknowledgment,
refund/settlement reconciliation and the full normal paid lifecycle are not
proven. The adapter correctly does not infer capture from Woo's payment method
or a transaction-shaped string. Do not fabricate financial evidence to bypass
this gate. Automatic webhook/n8n routing and customer/address crosswalk automation
also require isolated installed acceptance; this exercise uses an explicit
per-order reviewed customer, prices and commercial draft.

## Official Clover preparation

The official `clover-payments-for-woocommerce` 2.3.2 archive was downloaded from
WordPress.org and verified against SHA256
`c0c58e50c905b5bcbfa55b72c0aa178a6fb5b9eb2cebd9b013f6c7618754e4f5`.
Installed PHP bootstrap and gateway registration pass on WordPress 7.1.4,
WooCommerce 11.2.1 and PHP 8.3.36. This is runtime loading evidence, not full checkout
compatibility certification (the directory lists testing through WP 6.9.11).

The plugin is active, gateway **disabled**, environment `sandbox`, Apple Pay off,
debug logging off, no keys/Merchant ID configured, and gateway unavailable.
Existing external HTTP/mail/cron/payment blocks remain. No payment request ran.

Official documentation says the plugin is free and transactions use the existing
merchant agreement. This does **not** prove this merchant package's Ecommerce
entitlement, fees after Ecwid cancellation, or token availability. Required inputs
are the sandbox Merchant ID and Ecommerce Hosted iFrame + API/SDK public/private
keys; the existing general Clover access token is not a substitute. There is no
evidence justifying a subscription upgrade. Do not rotate/delete merchant tokens,
change a plan, enable production, or add catalog synchronization for this test.

Sources: [official plugin](https://wordpress.org/plugins/clover-payments-for-woocommerce/),
[Clover Woo documentation](https://docs.clover.com/dev/docs/woocommerce),
[configuration](https://docs.clover.com/dev/docs/configuring-the-clover-payment-extension),
[Ecommerce API token setup](https://docs.clover.com/dev/docs/setting-up-an-api-token).

## Reproducible commands and receipts

Run each command separately under the command-scoped lock. Exit 75 means switch
to repository work. `.test-deployment` is the **directory**, not its `.env` file.

```sh
~/bin/test2-console-lock commerce -- sudo -n python3 /home/rootedops/RootedOps-tax-run/scripts/commerce_tax_fixture.py /home/rootedops/RootedOps/.test-deployment
~/bin/test2-console-lock commerce -- sudo -n python3 /home/rootedops/RootedOps-tax-run/scripts/commerce_clover_prepare.py /home/rootedops/RootedOps/.test-deployment
# Fresh database ONLY: refuses an existing database; do not repeat on this installation.
~/bin/test2-console-lock commerce -- sudo -n python3 /home/rootedops/RootedOps-tax-run/scripts/commerce_installed_order.py /home/rootedops/RootedOps/.test-deployment --prepare-schema /home/rootedops/MushroomProcess-commerce-run
# One order ONLY: refuses an existing exercise receipt rather than creating duplicates.
~/bin/test2-console-lock commerce -- sudo -n python3 /home/rootedops/RootedOps-tax-run/scripts/commerce_installed_order.py /home/rootedops/RootedOps/.test-deployment
# Cancellation already executed. Repeating reads the completed receipt.
~/bin/test2-console-lock commerce -- sudo -n python3 /home/rootedops/RootedOps-tax-run/scripts/commerce_installed_order.py /home/rootedops/RootedOps/.test-deployment --cancel
```

Private receipts on test2: `tax-readiness/native-components.json`,
`clover-readiness/prepared.json`, and `installed-order/{state,received,approved,erp,result,final-audit}.json`
under `.test-deployment/private/`. The initial schema execution stopped on a psql
relative include; the same empty database was resumed without reset using `-f`
and copied upstream SQL files. The committed command preserves include paths.
A receipt serialization failure after committed delivery was recovered with
`--recover-receipt`, which reads the completed effect; no new order was created.
That recovery flag applies before cancellation only and is not needed now.

All observed lock periods released automatically. No production cutover,
subscription change, shared infrastructure rebuild or restored database reset
occurred. Roll back by disabling the Clover plugin (not uninstalling it), keeping
payments off, disabling the tax fixture as described in its runbook, and retaining
the cancelled order/isolated database for audit. Do not reset accounting history.

Production remains no-go pending the operational gates above. The reversible
[production plan](commerce-production-cutover-plan.md) is ready for owner review.
