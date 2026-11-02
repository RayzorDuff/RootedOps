# Test2 real Ecwid catalog expansion — executed November 2, 2026

**All nineteen prepared real products imported successfully** in the existing
5/5/5/4 batches. Installed coverage is now **22 ERP Items/commercial-content
records, 22 Woo products and 22 reconciled USD Item Prices**, including the three
original products. This is installed Test2 evidence, not mocked acceptance.

Baseline main: `a82b1af59eb7bb33fef928c4d3f0ce194fbb7822` (#53).
Imports executed candidate `261160e5954026cdbd527f4e179b59c72ec7f248`;
pilot gallery reconciliation passed at `016cb84bab88a3a3bde9bef8186ff505b4e08145`;
final catalog/binary audits and JPEG reuse passed at
`23f73766c74ac35bf2ac997f249349985c81012a`. PR #54 contains these changes.
Execution checkout: `/home/rootedops/RootedOps-catalog-run`; the older shared host
checkout and shared service configuration were preserved.

## Installed reconciliation

Every new record passed the existing installed ERP `import_product`/`catalog`
and Woo `upsert_draft` paths twice, retaining identities and record counts.
Verified title, descriptions, both SEO metadata fields, source keys/SKUs,
category mappings, original-media associations/order and authentic source prices.
Each Item has exactly one price in `Ecwid Catalog Pilot USD`; final global reads
found exactly 22 real migrated products in both destinations, with no duplicate
source identities or Woo SKUs. Products are draft/hidden, managed stock zero,
backorders disabled for new imports; mappings remain disabled.

| Ecwid product ID | Woo ID | USD | Gallery images |
| --- | ---: | ---: | ---: |
| 610276905 | 28 | 14.95 | 3 |
| 610274979 | 29 | 14.95 | 1 |
| 610276199 | 30 | 9.95 | 2 |
| 610276670 | 31 | 14.95 | 3 |
| 610274451 | 32 | 9.95 | 2 |
| 610277365 | 34 | 9.95 | 2 |
| 610277364 | 35 | 9.95 | 2 |
| 711335071 | 36 | 9.95 | 0 |
| 711334877 | 37 | 14.95 | 0 |
| 610276912 | 38 | 14.95 | 3 |
| 711335797 | 40 | 9.95 | 2 |
| 711335075 | 41 | 9.95 | 2 |
| 711335798 | 42 | 9.95 | 2 |
| 711335795 | 43 | 9.95 | 0 |
| 711335076 | 44 | 9.95 | 2 |
| 753212607 | 45 | 14.95 | 0 |
| 829845573 | 46 | 9.95 | 1 |
| 828374469 | 47 | 9.95 | 2 |
| 828374466 | 48 | 9.95 | 1 |
| 610274980 (original pilot) | 18 | 14.95 | 3 |
| 610274742 (original pilot) | 20 | 9.95 | 2 |
| 711334880 (original pilot) | 22 | 9.95 | 2 |

The complete original SKU/ERP Item/Item Price/ID map is in private
`catalog-expansion/catalog-audit.json`. Original pilot prices, descriptions,
categories, SEO and immutable CSV source payloads were preserved when updating
only their galleries; no three-product content/pricing reimport was needed.

## Media acceptance and real corrections

37 original source URLs resolve to **11 unique source binaries**, 11 Woo media
IDs and 11 ERP file URLs. They provide 37 gallery relationships across 18 products;
four source products have no image. Shared source binaries intentionally reuse
media across products; no product repeats an image ID within its gallery.
All requested downloads/uploads completed; original-image order passed read-back.

Woo retained originals match archived source SHA-256 values. ERP PNGs retain those
bytes. Installed Frappe has `strip_exif_metadata_from_uploaded_images` enabled:
JPEG copies are verified against the deterministic installed `strip_exif_data`
transformation of the archived original, with both hashes recorded. Original bytes
remain archived privately. No privacy/security setting was changed to force byte
equality. Initial strict raw-JPEG equality correctly stopped the audit until this
installed transformation was identified and accounted for.

Frappe File metadata has multiple aliases referencing some identical physical
file URLs. These records were retained and every alias's stored bytes verified;
no broad cleanup/deletion was attempted. Upload reuse now looks up the installed,
EXIF-normalized content hash instead of an unnormalized filename. An installed
JPEG reuse probe left total File count **54 → 54**. Product replays themselves
preserved File counts and used existing Woo media IDs. Alias consolidation is a
low-severity metadata housekeeping item, not duplicate gallery content.

The first pilot gallery transaction rolled back at a read-back assertion because
Frappe child construction mutated the expected dictionaries. Passing a deep copy
fixed that comparison; native and Woo gallery replay then passed, preserving
original source payloads and all unrelated product fields.

## All-source coverage, variations and taxes

The retained public API source snapshot has 38 enabled full records and 94 disabled
placeholders. Its SHA-256 remains
`6599f6cbc4603641ced586b7e1811977e71cf725478ff42b34a3a6a2c6952993`.
This session inspected that real snapshot; it did not claim a new private/full
Ecwid export or alter Ecwid. All 38 enabled records contain empty `options` and
`combinations` fields. **No genuine enabled variations were found; zero were
migrated, and none were manufactured.** Prior three combination-endpoint receipts
remain separate evidence; new per-product combination endpoint calls were not
made here. Disabled/private variation completeness remains unknown.

| Coverage | Count | Disposition / severity |
| --- | ---: | --- |
| Migrated enabled records | 22 | Installed draft acceptance passed |
| Enabled, category Disabled | 12 | Held: generic POS dollar-value products, including NOTAX labels; owner classification before storefront projection |
| Enabled, uncategorized | 4 | Held: category review; IDs 711333863, 711335072, 711334876, 711335074 |
| Failed product imports | 0 | Successful products retained through corrections |
| Disabled original records | 94 | Original CSV IDs/SKUs/history retained; no sellable recreation |

The four image gaps are `711335071`, `711334877`, `711335795`, `753212607`.
They match the source's empty media and are medium-severity publication-content
gaps, not failed downloads. The 16 held enabled records are pending, not silently
discarded. The original 132-row CSV remains authoritative for historical disabled
identities; public placeholder fields must never erase it.

Tax **policy remains unresolved**. Source has 24 `default`/14 `zero` labels; those
labels and `taxable=true`/included-rate-zero objects do not establish destination
rates/exemptions. The new draft-only compiler deferral copies the authentic tax
object to metadata and marks `_rootedops_tax_mapping_pending=yes`, omitting target
tax fields/templates. Live Woo tax calculation was read as `no` before each
deferred import and at final audit. No rate, exemption or class mapping was guessed
or activated. Resolve actual Ecwid tax-class policy before publication/checkout;
this is a high-severity cutover gate, not a draft-preservation failure.

Final financial document counts: Sales Order 0, Sales Invoice 0, Payment Entry 0.
Installed Woo → commerce/n8n → MP → ERP order-flow acceptance and Clover sandbox
were not executed in this catalog session and remain separate cutover work.
No production changes, real payments, outgoing mail/webhooks, restored-database
reset, shared Appsmith/n8n change or SignatureGate resource modification occurred.

## Reproduction and private evidence

**Use only command-scoped locking.** The old interactive-shell lock syntax is
obsolete. Each successful command below automatically released its lock; failed
commands also reported release. If acquisition returns 75, stop that operation,
continue repository work and retry at a later natural boundary.

The four reviewed compiled-file SHA-256 values used for installed preflight/apply:

| Batch | Records | Compiled SHA-256 |
| --- | ---: | --- |
| 1 | 5 | a0d5fe4c4beaa7738966bc2d37936d2b2e5593fae4d5dde9f77f231f6fea858f |
| 2 | 5 | 7ad31d74c529279340e9913998abd98eec40e50dc3deffd0e4f43245622cb033 |
| 3 | 5 | 192612f1fbf386f6efde7b7f008969801d2fe7540af59bc32916bcb7df881309 |
| 4 | 4 | df03674670e2ac5e67691c12431ea7ee1c1f428cc0666e54f1e99a80a464117b |

Example executed sequence (repeat with the corresponding batch number/hash):

```bash
~/bin/test2-console-lock commerce -- sudo -n python3 \
  /home/rootedops/RootedOps-catalog-run/scripts/commerce_prepare_real_batch.py \
  /home/rootedops/RootedOps/.test-deployment --batch 1

# Default is read-only; the next invocation applies and internally replays.
~/bin/test2-console-lock commerce -- sudo -n python3 \
  /home/rootedops/RootedOps-catalog-run/scripts/commerce_catalog_batch.py \
  /home/rootedops/RootedOps/.test-deployment \
  /home/rootedops/RootedOps/.test-deployment/private/catalog-expansion/batch-1/compiled.json \
  --sha256 a0d5fe4c4beaa7738966bc2d37936d2b2e5593fae4d5dde9f77f231f6fea858f

~/bin/test2-console-lock commerce -- sudo -n python3 \
  /home/rootedops/RootedOps-catalog-run/scripts/commerce_catalog_batch.py \
  /home/rootedops/RootedOps/.test-deployment \
  /home/rootedops/RootedOps/.test-deployment/private/catalog-expansion/batch-1/compiled.json \
  --sha256 a0d5fe4c4beaa7738966bc2d37936d2b2e5593fae4d5dde9f77f231f6fea858f --apply

# Existing pilot: prepare batch 0, then gallery-only reconciliation.
~/bin/test2-console-lock commerce -- sudo -n python3 \
  /home/rootedops/RootedOps-catalog-run/scripts/commerce_prepare_real_batch.py \
  /home/rootedops/RootedOps/.test-deployment --batch 0
~/bin/test2-console-lock commerce -- sudo -n python3 \
  /home/rootedops/RootedOps-catalog-run/scripts/commerce_pilot_galleries.py \
  /home/rootedops/RootedOps/.test-deployment

# Read-only global catalog audit; add --media-batch 0 (through 4) for binary checks.
~/bin/test2-console-lock commerce -- sudo -n python3 \
  /home/rootedops/RootedOps-catalog-run/scripts/commerce_catalog_audit.py \
  /home/rootedops/RootedOps/.test-deployment
```

Private evidence under `.test-deployment/private/`:

- `catalog-expansion/batch-{0..4}/`: source plan/lineage, review, archived media,
  upload receipt, compiled document and `media-binary-audit.json`.
- `catalog-batches/<compiled-sha>-{preflight,applied}.json`: incremental installed
  ERP/Woo acceptance; preserves ERP commit checkpoint before independent Woo writes.
- `catalog-expansion/batch-0/gallery-applied.json`: three original gallery results.
- `catalog-expansion/catalog-audit.json`, `media-reuse-audit.json`: final global
  identities/prices/control counts and stable native File reuse.

Validation: seven focused offline tests passed; conversion regressions 16 tests
with one PHP skip; Python and embedded-native syntax checks passed. Installed
batch/pilot-gallery replay, five binary audits, global catalog audit and normalized
JPEG reuse passed. No broad predecessor database/synthetic order suite was rerun.
