# ERP-authoritative editorial projection to existing Woo drafts

RootedOps #2 / #20. This is the **reviewed projection contract**, not
automatic Woo publishing or a live checkout activation.

## Authority and non-goals

Source: authenticated `rootedops_commerce.api.catalog(item)` returns
`Commercial Product Content` (public title, long/short descriptions, SEO)
and the corresponding ERP Item. The 132 migrated canonical content records
and 132 native Item descriptions are already accepted; do not reimport Ecwid
or reconstruct source descriptions from Woo.

Destination: an **existing** product on approved
`https://shop-test.danks.store` or `https://shop-test2.danks.store`.
The caller must provide a private, reviewed exact Item/SKU, source-key and
Woo-ID receipt from the completed migration (not a guess or a SKU-only lookup).
The Woo product must be a simple product, draft, hidden, carry the exact
`_rootedops_source_key` provenance and match the receipt. A variation,
published product, ambiguous metadata, wrong SKU, wrong receipt, or ERP content
not in Draft status is refused before writes.

The only permitted Woo PUT keys are `name`, `description`,
`short_description` and two `_rootedops_seo_*` metadata entries. Existing
Woo metadata IDs are reused; all unrelated metadata stays intact. **Never**
change prices, tax classes/rates, SKU, IDs, publication flags, visibility,
images, categories, stock, backorders, payment, fulfillment or MP data.

## Operator workflow and acceptance

`integrations/commerce/editorial_projection.py` exports:

```python
from editorial_projection import sync_staging

# Request a read-only fingerprint from live, authenticated ERP catalog +
# private verified crosswalk and authenticated Woo edit-context GET.
preview = sync_staging(shop_origin, private_woo_auth, erp_catalog, receipt)

# After reviewing exact changed_fields and digest, and under the exclusive
# test2 commerce console lock, explicitly approve the current snapshot.
result = sync_staging(
    shop_origin, private_woo_auth, erp_catalog, receipt,
    approve_digest=preview["digest"]
)
```

This module takes a preauthenticated canonical ERP catalog response. It
does not fetch ERP data, discover Woo product IDs, store credentials, or
schedule a task. **Do not embed credentials in receipts, Git or CLI history.**
Default is read-only; an exact digest approval is required for PUT.
A stale or altered Woo snapshot refuses before writing. It performs no
automatic retry. After a PUT, it GETs the product again and verifies that
each editorial field matches ERP and all protected Woo business fields
remain unchanged. Unexpected read-back after a successful remote PUT is
reported for operator reconciliation, not an automatic reversal or retry.

The code is a *reusable adapter* to connect to the authenticated staging
operator and future webhook-driven sync worker after native acceptance.
It has **not** been executed against a live Woo shop; it is not yet
a scheduled sync, a button inside ERPNext, or production cutover proof.

Test2 acceptance before enabling writes:
- Verify source receipt identity, staging hostname and exact source SKU.
- Read-only preview on representative food and cultivation supply drafts.
- Make an approved ERP content edit from the Item UI PR #73, fetch the
  latest canonical ERP response, preview differences, approve one draft
  editorial change and compare Woo edit-context + rendered SEO.
- Confirm repeated preview has no changes and duplicate approval is safe.
- Introduce a concurrent Woo edit and verify fingerprint rejection.
- Confirm prices, stock, visibility, categories, images, tax, provenance,
  MP inventory/reservations and ERP financial records are unchanged.
- Retain Woo/ERP before/after receipts and record a rollback for content
  only; do not roll back inventory or historical order records.
- Explicitly verify the 13 excluded generic POS codes remain unpublishable.

The next implementation should integrate this adapter with a private
operator workflow, persisted sync receipts, ERP content-modified checkpoint
and per-channel delivery state. No auto sync should be enabled until test2
acceptance and replay/idempotency evidence pass.
