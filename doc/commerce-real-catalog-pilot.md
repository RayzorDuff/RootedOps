# Real Ecwid catalog pilot

## Coverage checkpoint — November 1, 2026

Baseline RootedOps main `1183f10` includes PRs #48 and #49. Installed commerce
0.3.1 and native ledger verification are completed predecessors, not repeated here.

**Destination imports in this session: 0.** The exclusive Commerce Lish lock was
unavailable; no server actions followed that refusal. Source preparation is not
destination acceptance. No shared data, product publication or payment settings
were changed. The next session should resume this pilot rather than add another
synthetic catalog fixture.

Source: `products_2026-10-29_03-23 (1).csv`, SHA-256
`347660a5c4ccf3d434a8beda02c63e2d137871224d2ddfbf85f8e84b27f9d2bf`.
132 product records pass structural planning. The catalog-only converter now needs
no customer/order export; omission explicitly records `orders_export_supplied=false`
and does not establish an empty or complete historical order archive.

Candidate namespace `95802503` is observed in the exported Ecwid CDN image paths.
Verify it against the store's configured identity before the first destination
write; do not use an invented temporary namespace and later create duplicate Items.
The catalog-only source plan digest is
`678a6199d4ab8d70130167fc93683832c21b925c9fe942845b37fae2eb8c6200`.

| Ecwid product ID | Original SKU | Product | Export price | Images | Description / SEO |
| --- | --- | --- | --- | --- | --- |
| 610274980 | M5P9B1D6Q8R2S | Blue Oyster Grow Kit – Ready to Grow | 14.95 | 1 | Present / present |
| 610274742 | cdbd6f64-2637-488c-b9fc-0a5a47bb7322 | Blue Oyster Liquid Culture Syringe | 9.95 | 1 | Present / present |
| 711334880 | E3ZY47P9K64TT | Freeze Dried Blue Oyster Mushrooms | 9.95 | 1 | Present / present |

The first two export tax code `default`; the third exports `zero`. Preserve these
source values. Currency, ERP tax templates and Woo tax classes must be checked
against test2/store configuration; neither prices nor tax labels prove a tax rate.
All three are enabled in Ecwid, but destination publication must remain Draft.

## Source gaps and access blockers

- CSV has no complete variation/option definitions. Do not assume `_combinations=[]`
  means a verified simple product. Check the three candidates against a read-only
  Ecwid product/combinations export before declaring their type reconciled. Add a
  real variable family to the pilot when those definitions are available.
- CSV contains only primary images, not a verified gallery. All three selected
  primary images exist as exported URLs. Local image archival was attempted but
  CDN DNS resolution was unavailable; no image bytes or successful uploads claimed.
  Retry the existing archiver from the authorized test host without enabling app
  container egress or disabling isolation.
- Full export: 83 products have no image; among 38 enabled products, 18 have no
  image and eight lack each SEO field. Report these as source gaps, not silently
  generated replacements. Category `Disabled` must not be treated as approval to
  publish merely because its source product has enabled=yes.
- Lish reported `Console is reserved by another session.` Respect the current
  owner; do not remove the file, bypass flock or forcibly detach a Screen session.
  Resume after that owner releases its locking shell normally.

## Incremental procedure

1. Acquire `~/bin/test2-console-lock commerce`, attach only `screen -r commerce`,
   verify the expected test2 host, latest main and existing private configuration.
   Do not recreate the stack or restore databases. Release the lock afterward.
2. Confirm source store identity, currency and real variation definitions. Retain
   the original immutable export and its hash privately; preserve original SKU
   strings, including leading zeroes.
3. Convert catalog only, then select exact source identities with the existing
   reviewed compiler. A selected variation automatically includes its template
   and exported siblings. Full source/review hash binding remains intact.

```bash
python integrations/commerce/ecwid_csv.py \
  --products /private/products.csv --store-id 95802503 \
  --output /private/catalog-source.json --plan-output /private/catalog-plan.json
python integrations/commerce/migrate_reviewed.py catalog \
  /private/catalog-plan.json /private/catalog-review.json \
  --source-key ecwid:95802503:product:610274980 \
  --source-key ecwid:95802503:product:610274742 \
  --source-key ecwid:95802503:product:711334880 \
  --media-manifest /private/uploaded-media.json --output /private/pilot-reviewed.json
```

4. Use existing `media.archive` / `media_upload.upload` for checksum-verified blobs
   and scoped upload receipts. Reconcile any interrupted upload by checksum
   filename before retry; do not duplicate remote attachments. Populate reviewed
   category IDs, ERP UOM/group/price list, taxes and attributes from actual staging
   records, then compile. Missing mappings/media refuse before product writes.
5. Apply compiled records through installed `rootedops_commerce.api` and the
   existing `channel.upsert_draft`. Do not create a parallel import path. ERP source
   archives/content must retain source payloads; ERP Items/Prices reject existing
   identity/rate drift. Keep mappings disabled and content/products Draft. Do not
   use Ecwid quantity as operational stock: MushroomProcess remains authority.
6. Read both destinations after each family: compare source identity, exact SKU,
   variation parent/options, descriptions, price/currency, category/tax mappings,
   media references and SEO metadata. Record sanitizer transformations explicitly.
   Retry the same family and verify identical IDs and unchanged counts before
   expanding. Log each failure and its corrective action instead of skipping it.
7. Save a private receipt with source/review hashes, source → ERP/Woo identities,
   media checksums, parity fields and retry counts. Publish only aggregate coverage
   and non-sensitive product discrepancies to issue #20. Expand by complete family
   in small batches; checkout completion is not a prerequisite for draft imports.

## Separate checkout and cutover gates

Once console access is available, perform one synthetic installed Woo order through
existing ingestion into an isolated MP test ledger and native ERP service. Verify
paid-at-creation, dedupe and financial identities without rerunning the entire
synthetic framework. This session performed no installed order-flow actions.

Ecwid retirement remains blocked on real variant/gallery coverage, destination
parity, reviewed taxes/currency, customer/history handling, installed order and
fulfillment/financial reconciliation, Clover sandbox/merchant entitlement, URL/QR
redirects and an approved reversible production cutover. Draft catalog migration
should continue independently as access and source definitions become available.
