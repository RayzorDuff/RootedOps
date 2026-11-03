# Ecwid → ERPNext production / WooCommerce staging: 22-product acceptance

**Status:** Accepted — 2026-11-02 operator execution and independent reconciliation.  
**PR:** #57 (`feature/commerce-full-catalog-staging-preflight`)  
**Source store:** Ecwid `95802503`  
**Installed ERPNext:** `erp.danks.store`, rootedops_commerce `0.3.1`  
**Staging storefront:** `shop-test.danks.store`, private/Coming Soon

## Final acceptance evidence

The owner executed all five batches using `scripts/commerce_production_draft_import.py`
and individually verified the resulting ERPNext and WooCommerce records with
`scripts/commerce_verify_production_pilot.py`. Each independent verification
reported `"reconciliation": "PASSED"`, `"receipt_matches": true` and
`"writes": false`. This document records the **operator-reported outputs**;
the private receipt files are deliberately not committed to Git.

| Batch | Source products | Compiled SHA-256 | Cumulative ERP Items | Woo drafts |
| --- | ---: | --- | ---: | ---: |
| 1 | 5 | `ed49bd43b49cb9f705bd780f5f8d2220bd7aec32b2e4cc17c7dbde1a53f389d6` | 5 | 5 |
| 2 | 5 | `33bce3ae33935042eff78084b8913ad5ef60e1b9b7926a3686d99d691e83d90e` | 10 | 10 |
| 3 | 5 | `628b092e98ad926d7ceff0216fc207a03e4a7c7419526abe75043625f0ac277f` | 15 | 15 |
| 4 | 5 | `125f79a87369fb858cb99cae46b4726775e4b2965c1789332da26476914e9418` | 20 | 20 |
| 5 | 2 | `0c7cf15456337d665cbf48fdcfca56e1e1a67fc46b3c7f82bcbd1af78dfda052` | 22 | 22 |

At the final batch-5 reconciliation:

- ERPNext: **22 Item**, **22 Commercial Product Content**,
  **22 Commerce Channel Mapping**, and **22 Item Price** records.
- WooCommerce: **22 drafts**, **0 published products**, including final
  WooCommerce IDs **44** and **45** for Ecwid IDs `828374469` and
  `829845573`.
- No created ERPNext Sales Orders, Sales Invoices, Payment Entries,
  Stock Entries or Bins (each count **0** at final reconciliation).
- **37 ERPNext File records** in the production database at final read-back.
  Media preparation uploaded 11 unique image binaries and mapped 37 original
  source image URLs to ERPNext File / WooCommerce attachment identities.
- Individual import receipts for all five batches were checked against native
  ERPNext and WooCommerce read-backs. Product source identity, USD prices,
  metadata, galleries and draft-only safety conditions passed.
- Four pilot products were missing original source images; the owner accepted
  these source gaps rather than treating them as migration blockers.
- WooCommerce remained unpublished/Coming Soon, out of stock, payment gateways
  inactive, tax calculation disabled pending reviewed tax configuration.
- Last checked PR #57 commit `f6bd83e` had passing **Commerce foundation**,
  **Fresh host recovery** and **Commerce integration contracts** workflows.

## Preserve private recovery material

The operator retains, outside Git, under `~/commerce-migration/`:

- `ecwid-full-catalog-source.json` — the 132-source-product export,
  SHA-256 `0b4eec40a1cfd1d62551e2ac951a42dac21984f34ffb2d03f9aea697d1d713a8`.
- `media-archive/` — verified source binary archive.
- `media-preparation-1/upload-manifest.json`, `uploaded-media.json`,
  `media-upload-receipt.json`, reviewed plan and review files.
- `pilot-batches-1/pilot-01.json` through `pilot-05.json` and `batch-index.json`.
- `media-preparation-1/pilot-01-import-receipt.json` through
  `pilot-05-import-receipt.json`.

Do not commit sensitive source snapshots, credentials, or private receipts to Git.
Do not delete or overwrite them during PR cleanup. The separate
`~/RootedOps-commerce-pr57` worktree has the implementation used for acceptance.

## Scope and next engineering priorities

**Accepted:** The exact 22-product reviewed cohort, reproducible source plan,
media mapping, installed draft import, checksum-bound operator receipts and
independent installed reconciliation. Do not repeat broad migration coverage
merely to increase product counts.

**Not yet approved:** Publishing the WooCommerce catalog, enabling checkout,
tax computation, active commerce sync, saleable inventory, historical order
imports, or retiring Ecwid. The remaining **110** source records are outside
this accepted cohort; of the **16** additional enabled Ecwid records, 12
appear to be generic POS/Disabled-category products and four uncategorized.
Classify these separately; do not block the principal storefront workstream.

**Priority A:** Native ERPNext v16 tax setup for Dank Mushrooms in Johnstown,
Colorado, starting from correct current jurisdiction and product treatment,
not Ecwid's unverified legacy tax settings.

**Priority B:** Installed WooCommerce → MushroomProcess → ERPNext order flow,
including stable order identities, reservations, partial shipments, financial
records and replay/integration acceptance under safeguards.

**Priority C:** Clover WooCommerce sandbox checkout integration, including
gateway and reconciliation contracts. Keep staging checkout/payment
operations disabled until explicitly tested and authorized.

The accepted pilot remains a draft-only product migration, not a live
end-to-end order or payment acceptance test.
