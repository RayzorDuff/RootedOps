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
The export also independently confirms store ID 95802503. The API returned 132 identities: 38 enabled full records and 94 disabled
placeholders. All 38 enabled records reported empty options/combinations; each
pilot combination endpoint independently returned an empty list. Disabled variation
completeness remains unknown. No actual pilot variations exist to migrate; do not
manufacture variations to satisfy a testing target.

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

## Executed installed acceptance

Pricing command commit `7d6f0345ded2bd8e0bb1dab162c125f02b880047` ran on test2
from `/home/rootedops/RootedOps-price-run`. Read-only preflight, apply and subsequent
read-only reconciliation passed. The apply itself repeats both ERP import and Woo
upsert. Each Item has exactly one matching Item Price; Woo identities stayed stable.

| SKU | ERP Item Price ID | Woo ID | USD rate |
| --- | --- | --- | --- |
| M5P9B1D6Q8R2S | 51dh7jssbr | 18 | 14.95 |
| cdbd6f64-2637-488c-b9fc-0a5a47bb7322 | 51dd36tc1u | 20 | 9.95 |
| E3ZY47P9K64TT | 51e8nrhi2a | 22 | 9.95 |

An initial Woo comparison stopped after the first price update because GET view
context paragraph formatting differed from PUT edit context. Existing ERP prices
had already committed. Correcting GET to authenticated edit context allowed strict
content equality checks and a safe repeat; no content-recovery overwrite occurred.
The final pass preserved descriptions, short descriptions, images, categories,
draft/hidden visibility and managed stock zero. No new Item or financial documents.

Private application receipts: `.test-deployment/private/ecwid-pilot/prices-applied.json`
and `prices-preflight.json`. Use the absolute script path above for the documented
commands until the owner merges this PR; the main host checkout/configuration was
preserved. No shared service restart or infrastructure/security setting change.

Live API profile independently verified store 95802503 and currency USD. Public
catalog file SHA-256:
`6599f6cbc4603641ced586b7e1811977e71cf725478ff42b34a3a6a2c6952993`.
It is a later live snapshot, not the original October CSV. The full API planner
flags missing SKUs on all 94 disabled placeholders; do not overwrite original CSV
identities with those absent fields or treat the public response as a full private
export. Enabled products retain 24 default and 14 zero tax-class labels. All three
pilot API tax objects report taxable=true, no enabled manual taxes and included
rate zero; these fields do not authorize an invented destination tax policy.

API gallery inventory has 21 entries. Corrected pilot planning retains seven
original media URLs across the three products (LC 2, grow kit 3, freeze dried 2),
archived successfully under `commerce-ecwid-read/pilot-original-media/`. These seven
originals are **not yet applied** to destination galleries; the previously imported
three primary images remain. API subtitle mapping is also corrected in the planner
for future batches; this source change is regression-tested but not yet applied
to a new destination batch. Original CSV payloads remain immutable.

Enabled category inventory: 14 Grow Kits and Mycology Supplies, eight Gourmet
Mushrooms, 12 Disabled, four uncategorized. After excluding the three existing
pilot products, 19 candidates are recorded in private `batch-candidates.json` as
5/5/5/4 records. This is preparation, not import acceptance. Hold the 12 Disabled
category and four uncategorized records for review; retain 94 disabled CSV records
as archives until an adequately scoped source export is available.

Current verified migration coverage remains **three products / three prices / zero
actual pilot variations**. Full original galleries, reviewed taxes and subsequent
batches remain open. Installed order-flow and Clover sandbox acceptance did not
run in this session. All source calls were GET-only; no Ecwid changes. Commerce
Screen was detached and the locking shell explicitly exited after server work.
