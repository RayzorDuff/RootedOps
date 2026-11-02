# Real catalog pilot pricing and source reconciliation

Continuation baseline: main `fe8cf451f67a09de77d6d81420037506e53749e4`, including
PRs #48–#51. Preserve the actual three-product content/media evidence in
[commerce-real-pilot-executed.md](commerce-real-pilot-executed.md).

## Repeatable price application

The user confirmed USD. The existing three source prices are 14.95 (grow kit),
9.95 (LC syringe) and 9.95 (freeze dried). `scripts/commerce_pilot_prices.py`
preflights exact existing source/SKU/rate identities, disabled ERP integrations,
private container networking, draft hidden Woo products, zero stock and USD store
currency. It never creates a product, restores a database or changes sudo settings.

After acquiring the Commerce console lock and attaching Commerce Screen:

```bash
sudo -n python3 scripts/commerce_pilot_prices.py /home/rootedops/RootedOps/.test-deployment
sudo -n python3 scripts/commerce_pilot_prices.py /home/rootedops/RootedOps/.test-deployment --apply
```

Default is read-only. Apply uses the installed ERP importer twice for each Item
Price and existing Woo channel adapter twice for each price. It verifies no extra
ERP Item/financial documents, one price per pilot Item/UOM/list, stable Woo IDs,
unchanged descriptions/images/categories/visibility/stock and exact decimal rates.
Receipts go privately under `ecwid-pilot/prices-preflight.json` and
`prices-applied.json`. ERP and Woo writes are separate transactions: if Woo fails
after ERP commits, inspect the private receipt/state and repeat the same guarded
command; do not recreate products or restore databases. Existing conflicting prices
require explicit reconciliation rather than overwrite.

This pricing pass does not assert complete tax/variation acceptance. Existing tax
settings are preserved and publication/payment controls remain disabled.

## New source evidence

Read-only Ecwid API catalog access succeeded using the public catalog token from
the supplied control-panel export; no secret token or merchant-setting changes.
The export also independently confirms store ID 95802503. The API returned 132
products, 38 enabled, with zero products reporting options or combinations. Do not
manufacture a variation to satisfy a testing target. Dedicated combination checks
and fuller gallery reconciliation should determine whether any variation work is
applicable to this actual catalog.

The grow kit has two gallery entries, exceeding the CSV's single image. API source
also distinguishes original images from resized primary images. The planner now
prefers original URLs and deduplicates identical originals so a resized primary
is not imported alongside its own original as another gallery photo. Original API
payloads are retained; CSV archives are not overwritten.

Private read-only API receipts on test2:
`/home/rootedops/.local/state/commerce-ecwid-read/` (`profile.json`,
`public-products.json`, individual product/combination replies when successful).
These contain no customer/order exports. Do not commit tokens or full source data.
The public catalog snapshot is not evidence of private-field completeness.

## Next ordered actions

1. Apply and reconcile pilot USD prices with the guarded script.
2. Read combination endpoint receipts; record actual variation count without
   treating unavailable fields/endpoints as zero.
3. Compare original/gallery image URLs, archive missing originals and update only
   the reviewed pilot gallery. Retain initial CSV source payload/history.
4. Review default/zero tax semantics; source tax class is not a tax rate. Preserve
   original category IDs/paths and resolve destination categories explicitly.
5. Expand in small complete-family batches using the existing reviewed compiler.
6. Keep installed order/Clover acceptance separate from draft catalog imports.

Use the lock briefly for server tasks. If unavailable, continue repository work
and retry at a task boundary. Detach only Commerce Screen and explicitly exit the
locking shell before stopping.
