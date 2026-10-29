# Commerce migration foundation (RootedOps #20)

This is an initial development release, not a cutover tool. ERPNext owns Item,
Item Price and commercial content. MushroomProcess owns quantities and lineage.
Clover remains the checkout provider; no Moov implementation is included.

## Export and reconcile

Use a read-only Ecwid token with catalog, customer and order read scopes. Tokens
come from environment variables, never CLI arguments or committed files.

```bash
mkdir -p integrations/commerce/private
chmod 700 integrations/commerce/private
python3 integrations/commerce/ecwid_migrate.py export --store-id 95802503 --output integrations/commerce/private/source.json
python3 integrations/commerce/ecwid_migrate.py plan integrations/commerce/private/source.json --output integrations/commerce/private/plan.json
```

`ECWID_TOKEN` is required for export. Export paginates products, customers, orders
and categories, collects each product's combinations and store profile, and
preserves complete source JSON. Reconciliation detects missing/duplicate SKUs
and duplicate identities. Export must run during a stable source window; count
changes cause failure. Same-count concurrent source edits still require a second
export/hash comparison with source edits paused before final cutover.

The plan retains variant options, category IDs, source enable state, prices,
HTML descriptions, SEO and image references. Source data hashes and stable keys
make repeated plans deterministic. Files are written with mode 0600.

## Reviewed ERP import

Install `rootedops_commerce` first. Do not install Frappe Webshop. Review Item
codes, Item Groups, UOMs, variant attributes, currency, price lists and taxes.
The authenticated POST method
`rootedops_commerce.api.import_product` accepts `content`, `item`, `mapping`, and
an optional reviewed `price` object (`price_list`, `currency`, `item_price_rate`).
It creates non-stock ERP Items only, drafts commercial content, and inserts
channel mappings disabled. It never changes operational stock. Repeated source
identities resolve existing records; source/content or price drift blocks the
transaction. Existing Items remain unchanged. Concurrent unique-key conflicts
roll back; retry the entire request. Sales Manager/System Manager role plus
DocType create/read permissions are required. No guest access or permission bypass.

The CLI `apply-erp` imports content and immutable customer/order/category/profile
archives **against existing reviewed Items only**, using a JSON map from source
SKU to ERP Item Code:

```bash
python3 integrations/commerce/ecwid_migrate.py apply-erp integrations/commerce/private/plan.json \
  --base-url https://erp-test.danks.store \
  --item-map integrations/commerce/private/item-map.json --allow-staging-write
```

`ERP_AUTHORIZATION` contains `token API_KEY:API_SECRET`. Writes are restricted to
the staging hostname. Source archives are not ERP Customers, Sales Orders or
Invoices. This deliberately prevents historical email, accounting and fulfillment
replay. Converting archives into operational records remains a separate reviewed
migration, including duplicate-customer policy and existing-accounting matching.

## WooCommerce projection

`channel.py` supplies a testable draft-only upsert adapter restricted to
`shop-test.danks.store`. It resolves exact SKUs and verifies migration provenance
before updating. Variable products require reviewed attributes and parent IDs;
no synthetic SKUs or guessed options. SEO is preserved in private metadata;
a chosen SEO plugin adapter must expose it in storefront markup. Prices and tax
mappings must be reviewed before adding them to projection payloads. Inventory
writes remain disabled until a validated MushroomProcess snapshot is joined to
ERP content and mappings using `compose_projection`.

## Outstanding acceptance gates

- Obtain read-only Ecwid token/export and reconcile actual source counts.
- Download and checksum image binaries, including original gallery/variant media;
  URL preservation alone is not an offline archive. Validate redirects before download.
- Review product/variant/GTIN, category, currency, tax and Item Price mappings.
- Validate Frappe installation, migrations, role/user permissions and concurrent
  retries on a disposable v16 site. Run `bench --site <test> run-tests --app rootedops_commerce`.
- Implement live customer/order conversion and authenticated WooCommerce webhook
  processing with durable idempotency, stock reservations, refunds and replay tests.
- Install reviewed WooCommerce/Clover plugin versions and test sandbox checkout;
  merchant entitlement and fees require merchant-account verification.
- Back up and restore DB + media; compare fields/counts and old product URL redirects.
- No production import, DNS cutover, subscription cancellation or merchant changes
  are performed by these tools.
