# Repository-only commerce migration (app 0.2.0)

Scope: RootedOps #20/#2/#3/#26 and MushroomProcess #80/#85/#86. The old temporary
Linode is deleted. Its databases, keys and volumes are not prerequisites and must
not be probed or reconstructed. All examples below use synthetic fixtures; the
new features are inactive until explicitly configured on a later staging site.
RootedOps #22 remains the fresh-host recovery and deployment acceptance procedure.
No production, DNS, subscription or merchant configuration changes are included.

## Reviewed products

Run from repository root:

```sh
python3 integrations/commerce/migrate_reviewed.py catalog \
  integrations/commerce/fixtures/catalog-plan.synthetic.json \
  integrations/commerce/fixtures/catalog-review.synthetic.json \
  --output /tmp/catalog-reviewed.json
python3 integrations/commerce/migrate_reviewed.py history \
  integrations/commerce/fixtures/history-source.synthetic.json \
  integrations/commerce/fixtures/history-review.synthetic.json \
  --output /tmp/history-reviewed.json
make commerce-test
```

The catalog compiler binds review to the Ecwid plan's source digest and requires
explicit source-currency confirmation, selling price list, per-SKU ERP Item/UOM/
group, source-category → Woo category IDs, tax treatment and variant attributes.
Templates precede variants; only leaves get Item Prices. Missing/unknown values,
colliding ERP identities and incomplete variant assignments fail. Parent templates
cannot be sold as leaf Items. This compiler does not infer variants absent from
CSV; obtain API combinations or a complete reviewed enrichment first.

Create/review the destination Item Groups, Item Attributes and allowed values,
Price Lists, Woo category hierarchy/tax classes and Item Tax Templates first.
Category mapping reuses reviewed Woo IDs; automatic taxonomy creation and hierarchy
reconciliation are not claimed. ERP tax-account/jurisdiction semantics are operator
configuration; product tax classes do not implement checkout tax calculation.

After a new isolated Frappe site has migrated app 0.2.0, enable the site flag
`commerce_catalog_import_enabled` and POST the compiled JSON as the `payload`
argument to `rootedops_commerce.api.import_reviewed_catalog` using a least-privilege
Sales Manager token. Disable the flag afterward. The endpoint uses the existing
permission-aware importer in one POST transaction, refuses Item attribute/tax/
identity or price drift and never changes stock. Existing prices with ambiguous
validity require reconciliation. No explicit intermediate commits occur.

For Woo drafts, pass each compiled record and `variant_attributes` to
`channel.upsert_draft`; apply templates first, resolve the returned parent ID,
then variations. Review the stored parent mapping before sending a variation.
Exact SKU/source ownership and draft status guards still apply. Leaf regular
prices and tax classes now survive variation payload filtering. Production
hostname writes and publication remain disabled.

## Archived media and storefront SEO

Run the existing media archive helper with reviewed HTTPS CDN allowlists. Retain
the private binary archive and manifest before retiring Ecwid. The new
`media_upload.upload` preflights every checksum/size and supported raster signature,
rejects traversal/symlinks, SVG/HTML and unexpected destinations, and uploads to
Frappe File and WordPress media APIs on the explicit test origins only. Supply
separate staging authorization strings at runtime; never put them in a review file.
A private per-destination receipt skips successful uploads and can resume after
partial failure. A crash between remote success and receipt persistence can leave
an orphan upload: reconcile deterministic checksum filenames before retrying.
Duplicate archived blobs are reused. Original source URLs remain provenance.
Pass the returned enriched manifest to `compile_catalog`; every gallery image
requires an ERP File URL and a Woo media ID, so Woo cannot silently hotlink Ecwid.
Actual raster decoding/image safety and installed WordPress MIME restrictions
remain integration checks, beyond the signature/size boundary tests.

Install `wordpress/rootedops-commerce/rootedops-commerce.php` as a reviewed plugin
on the separate Dank Mushrooms storefront. It renders `_rootedops_seo_title` and
`_rootedops_seo_description` through WordPress title/head hooks, or through Yoast's
`wpseo_title`/`wpseo_metadesc` filters when Yoast is active. It strips tags, escapes
head attributes, retains fallback values and avoids a second description tag under
Yoast. This is storefront SEO only; it does not implement Google/Meta feeds or
other SEO plugins. No plugin is automatically installed or activated. Verify
rendered HTML, theme behavior, cache invalidation, canonical URLs and variations
in staging before publication.

## Operational historical customers and draft orders

The history compiler requires full source customer/order/line identities and a
source-digest-bound review. It never merges customers by email. Identity hashes
scope provider/store/entity/source ID. CSV-derived customers/order numbers remain
in their separate namespace; missing API IDs, currency or line IDs must be enriched
explicitly, never guessed. Guest orders need an explicit customer resolution before
this converter can accept them. Customer name/group/territory are converted;
Contact/Address documents and Woo customer accounts are not yet replayed.

Review net line amounts after discount allocation and separate actual tax/shipping/
fee accounts; the compiler reconciles their sum exactly to the exported order total.
It produces Customer records and **draft Sales Orders only**. No invoice, Payment
Entry, Delivery Note, stock ledger entry, email or fulfillment operation is emitted.
Source payment/shipping status stays in the immutable source/review payload.
Currency conversion, precision and ERP default taxes must still reproduce the
source total after ERP validation; otherwise the POST rolls back.

On a later staging site, enable `commerce_history_import_enabled` and POST the
compiled plan as `payload` to `rootedops_commerce.history.import_history`. A unique,
immutable Commerce Migration Identity maps each source to the created ERP document,
with complete private source/review JSON and fingerprint. Retries resolve the same
document; concurrent insertion loses the unique key and rolls back its POST before
retry. Drift or submitted/cancelled historical orders stop for reconciliation.
Never submit audit-only historical orders: that would create operational demand
that this milestone deliberately avoids. An explicit correction/amendment workflow
and comparison to preexisting ERP invoices/payments are cutover prerequisites.

## Woo order and Clover boundaries

`orders.normalize_woo` verifies the exact raw request bytes with base64 HMAC-SHA256
before JSON parsing, supports current/previous strong secrets, rejects duplicate
JSON keys, and resolves both Woo product/variation ID and exact SKU against a
reviewed operational map. The endpoint's configured site/secret supplies trust;
unsigned Source/Topic/Delivery headers are not authorization. Event identity is a
body SHA256. UTC modified timestamps order snapshots; same-second divergent updates
require authoritative refetch rather than an invented ordering. Include complete
refund snapshots. Invalid/missing mappings go to a private error queue, never
partial inventory mutation. Payloads normalize channel and processor separately.

There is no public HTTP listener or activated n8n workflow in this PR. The future
receiver must enforce TLS, body limits, configured shop/secret routing, signature
before parse, secret rotation, durable private error/retry storage and backpressure.
Persist the normalized snapshot through MushroomProcess migration 052 before
acknowledging delivery. Do not expose SQL directly to Woo. Woo completed is only a
fulfillment request. Operational movement and reservation release must be atomic
inside MushroomProcess; partial shipment/returns/expiry still need explicit review.

A Woo paid flag/transaction ID is not capture proof. `reconcile_clover` only matches
verified adapter evidence with exact site/order/payment ID, currency, captured gross
amount and cumulative refund amount. Authorize-only, amount/time guesses and
mismatches fail. The companion MP payment ledger prevents transaction reuse. These
functions do not implement a merchant fetch adapter, settlement fees, chargebacks,
Sales Invoice or Payment Entry posting. The `verified_adapter` marker is a trusted
internal contract, not cryptographic verification or a user-supplied assertion.

## Clover evidence and later deployment gates (#26)

Official sources reviewed 2026-10-29:

- Clover's [WooCommerce guide](https://docs.clover.com/dev/docs/woocommerce) identifies
  its supported Woo plugin and US/Canada scope.
- [WordPress distribution](https://wordpress.org/plugins/clover-payments-for-woocommerce/)
  identifies Clover eCommerce as author and lists authorization/capture/refund/void.
- [Clover configuration](https://docs.clover.com/dev/docs/configuring-the-clover-payment-extension)
  documents sandbox/production separation, merchant ID, public/private keys and
  authorize vs authorize-and-capture. Obtain keys privately through the merchant
  portal; do not put card data through RootedOps or MushroomProcess.
- The distribution and older Clover install guide list different minimum versions.
  Do not infer compatibility with the deleted host's runtime. Pin and review the
  then-current plugin/WordPress/Woo/PHP versions on the new staging host, inspect
  actual gateway/transaction/refund fields, and test classic/block checkout.
- [Woo webhook signature](https://developer.woocommerce.com/docs/apis/rest-api/v2/webhooks)
  and [Yoast filters](https://developer.yoast.com/customization/apis/metadata-api/)
  support the implemented boundaries. No Clover webhook signature algorithm is
  invented; it must follow the exact selected adapter/API specification.

Before Ecwid retirement: provider must confirm merchant entitlement, online payment
permission, account/credential continuity, fees and settlement after downgrade.
Then test sandbox success/failure, authorization/capture/void, abandoned checkout,
webhook redelivery/out-of-order events, reservation races, partial/full refund,
physical fulfillment/returns, ERP traceability and settlement. A separately approved
controlled live checkout and reversible cutover are still required. No Moov work.

## Validation and rollback

Local Python tests cover compiler failures, monetary reconciliation, source-scoped
identity, Frappe boundary retry/drift, signature tampering/rotation, variant mapping,
refunds, media receipts and capture contracts. Frappe behavior uses mocks here; a
fresh v16 site must run native integration tests and confirm transaction rollback,
concurrent uniqueness, permissions, tax/price precision and draft-only behavior.
The PHP boundary harness runs in GitHub Actions with fake WordPress functions;
rendered storefront integration is still pending. MP PostgreSQL CI tests native
transactions/concurrency separately. All fixtures are synthetic.

Rollback before activation: disable the two new site flags, stop the new worker,
deactivate the SEO plugin, and revert app code. Do not delete imported ERP audit
records or active reservations automatically. Retain migration identity/source
records for reconciliation. No bootstrap, Compose, restore or backup changes are
required by these inactive features; #22's clean-host acceptance remains separate.
