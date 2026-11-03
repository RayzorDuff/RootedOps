# Full Ecwid catalog — production-staging preparation

Scope: Ecwid store 95802503. User's 2026-11-03 API extraction found 132
products with 132 unique nonempty SKUs, no combinations, 38 enabled and 94
disabled; 22 have existing test2 draft acceptance. Three active category records
were fetched, while 12 enabled POS records cite missing category 199701664.
The user wants **all 132 products retained**. Ecwid remains authoritative.

## Read-only preflight

The source snapshot is operator-owned and private; never commit it. On production:

```sh
python3 scripts/commerce_full_catalog_preflight.py \
  "$HOME/commerce-migration/ecwid-full-catalog-source.json" \
  --output "$HOME/commerce-migration/full-catalog-preflight.json"
```

The report binds to the exact snapshot SHA, preserves all source IDs in
validated/other_enabled/disabled cohorts, and flags unresolved categories,
missing images, prices and descriptions. This script makes **no destination
writes** and does not replace the reviewed product compiler.

## Production import requirements / NOT YET IMPLEMENTED

- Existing `scripts/commerce_catalog_batch.py` is test2-only: DO NOT run it
  against production. Preserve its environment guards.
- Make a separately reviewed production-staging adapter with explicit domain,
  container identity, site and live operational safety checks (Woo Coming Soon,
  payment gateways off, tax treatment, no webhook delivery, ERP financial and
  stock baseline). Do not require maintenance-mode changes to payroll production.
- Run the 22 previously reconciled products first, then 16 other enabled and 94
  disabled products, in repeatable batches with receipts. Draft-only Woo, hidden
  catalog, zero managed stock, no backorders, Commerce channel mappings disabled.
- A disabled source record requires `include_disabled_drafts=true` and
  `draft_only=true` in the reviewed compiler. Its original `enabled` is retained
  in `content.source_payload` and Woo metadata `_rootedops_ecwid_enabled=no`.
  Future sync/publication must separately enforce the source-status field.
- Resolve unknown category 199701664 by explicit review. Never silently map
  to other categories; preserve source category ID in the original payload.
- Archive/upload unique media with hashes to both target systems before
  compiling products. Missing source images are accepted gaps, not placeholders.
- Verify SKU uniqueness, immutable Ecwid identities, original prices, taxonomy,
  source status, media ordering, and idempotent replays. Never import historical
  orders/payments or operational stock during catalog migration.
- Do not run a Commerce deploy on production until the Docker image includes
  the Commerce Python package and flit_core. PR #56 enforces an image preflight.
- Hold storefront publication pending native taxes, order routing and Clover
  sandbox checkout acceptance. Back up new WordPress DB/files off-host.

This PR is intentionally a *preflight and compiler-safety change*, not a
completed production importer or authorization to apply the 132 records.
