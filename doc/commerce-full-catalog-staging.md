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

## Reproducible first-cohort media and taxonomy staging

From the operator's private full Ecwid source (SHA
`0b4eec40a1cfd1d62551e2ac951a42dac21984f34ffb2d03f9aea697d1d713a8`):

```sh
python3 scripts/commerce_staging_media_inventory.py \
  "$HOME/commerce-migration/ecwid-full-catalog-source.json" \
  --output-dir "$HOME/commerce-migration/media-preparation-1"
```

This performs no network calls and creates restricted
`pilot-media-source.json` and `pilot-media-inventory.json`. The latter lists
the actual media hosts. After reviewing those hosts, use the existing
`integrations/commerce/media.py` archiver against the selected media source
with explicit `--allow-host` values. Never upload unverified binaries or commit
private source/receipts to Git.

## Verified first-cohort media destination transport

The owner prepared all 37 required media URLs and verified 11 unique archived
binaries. The upload manifest is private and its file SHA-256 is
`447302ab4fda29297d4c3e12060d2546ba529432997c0f9e6445239ba445c46f`.

`scripts/commerce_production_media.py` is the separately guarded transport:
it verifies every archived blob with the existing media validator, requires
exactly 37 source URLs and 11 binaries, and reuses Frappe's File deduplication
and WordPress's checksum attachment metadata. It keeps a private receipt
scoped to `erp.danks.store|shop-test.danks.store`. It does not create Items,
orders, payments or inventory transactions. The default mode performs no
remote writes.

From a separate review worktree containing PR #57, with `--repo-root`
pointing to the installed production RootedOps checkout:

```sh
python3 scripts/commerce_production_media.py \
  --repo-root "$HOME/RootedOps" \
  --manifest "$HOME/commerce-migration/media-preparation-1/upload-manifest.json" \
  --blob-dir "$HOME/commerce-migration/media-archive" \
  --receipt "$HOME/commerce-migration/media-preparation-1/media-upload-receipt.json" \
  --sha256 447302ab4fda29297d4c3e12060d2546ba529432997c0f9e6445239ba445c46f
```

**Do not use `--apply` until installed-container inspection, backup and
credential-free native transport compatibility are reviewed and approved.**
Writes are explicit via `sudo ... --apply`. The native ERP upload uses
`docker compose exec -T`, while the Woo upload runs inside the staging
WordPress container; no public ERP authentication token is needed. Frappe may
normalize JPEG metadata; receipt retains its normalized File URL and the
original source sha. Repeat runs use existing Frappe content hashes and
WordPress source-sha metadata to avoid duplicates. Preserve all receipts and
source images in private local state.

## Offline compilation of the first 22 reviewed products

After the verified 11 ERP File / 11 Woo Media uploads and 37 URL mappings,
prepare immutable five-product batches using the operator's current private
`review.json` (selling price list `Standard Selling`, not
`Standard Selling USD`):

```sh
python3 scripts/commerce_compile_production_pilot.py \
  --full-source "$HOME/commerce-migration/ecwid-full-catalog-source.json" \
  --plan "$HOME/commerce-migration/media-preparation-1/reviewed-plan.json" \
  --review "$HOME/commerce-migration/media-preparation-1/review.json" \
  --uploaded-media "$HOME/commerce-migration/media-preparation-1/uploaded-media.json" \
  --upload-manifest "$HOME/commerce-migration/media-preparation-1/upload-manifest.json" \
  --output-dir "$HOME/commerce-migration/pilot-batches-1"
```

The compiler validates the exact 132-product full source checksum and 37-URL
upload manifest checksum, 22 exact selected IDs, approved categories (16/17/18),
original prices/status, 11 unique binary checksums, source-to-upload mappings,
and the existing 5-record test2 batch validator. It deduplicates images by
source binary checksum within each product without altering the original
source payload. Five output batches contain 5/5/5/5/2 records. The output
directory must be empty and is private. **This is a read-only/offline step.**
Record each compiled-batch checksum from `batch-index.json` before any staging
product write.

## Installed first-batch readiness without changes

After the five offline batches are compiled, run this read-only installed
preflight from the PR worktree (keep the production checkout untouched):

```sh
python3 "$HOME/RootedOps-commerce-pr57/scripts/commerce_production_batch_readiness.py" \
  --repo-root "$HOME/RootedOps" \
  --compiled "$HOME/commerce-migration/pilot-batches-1/pilot-01.json" \
  --sha256 ed49bd43b49cb9f705bd780f5f8d2220bd7aec32b2e4cc17c7dbde1a53f389d6
```

It verifies the installed Commerce 0.3.1 API, native ERPNext site, approved
Item Group, UOM, USD selling Price List, the required public File records,
absence of collisions in ERP Items / mappings / prices and Woo SKU, correct
Woo categories, media IDs, store currency, Coming Soon, no published products,
no enabled checkout gateways and no active Woo webhooks. It does not import
Items or Woo products. The site is not placed in maintenance mode and
financial/stock records are not changed.

**Do not run the provisional production batch runner with --apply.** It still
relies on test2 REST credentials/targets and is intentionally write-blocked.
Develop a separate native staging Woo projection adapter (or a properly
authenticated, exact-origin-scoped adapter) with per-record replay receipt
before the first write.

## Native first five-product draft import

The first installed batch preflight passed: live ERPNext 0.3.1, price list
`Standard Selling`, five unique new source/SKU identities, uploaded public
Files, staging media IDs, Woo category mappings (16/17/18), USD, no enabled
checkout gateway or webhooks, no published Woo products. Baseline ERP Item,
Commercial Product Content, Commerce Channel Mapping and Item Price counts
were all zero; ERP File count 37. Preserve this preflight output.

`scripts/commerce_production_draft_import.py` is separate from the provisional
test2 adapter and accepts **only** the immutable first batch SHA-256
`ed49bd43b49cb9f705bd780f5f8d2220bd7aec32b2e4cc17c7dbde1a53f389d6`
with Ecwid IDs `610274451, 610274742, 610274979, 610274980, 610276199`.
It uses native Frappe `import_product` and Commerce `catalog` within a
single transactional five-product ERP operation. It refuses any mutation of
Sales Orders, Sales Invoices, Payment Entries, Stock Entries, Bins or Files.
Each product import is repeated within the transaction and verifies
idempotence. No production scheduler, payroll or mail settings are modified.

Staging WooCommerce is written through native WooCommerce CRUD from the
staging WordPress container, not an API credential. Each product is a
hidden, zero-stock, no-backorder draft with no Woo tax calculation. Existing
SKUs are reused **only** if their source metadata matches; replay also
verifies exact content, prices, categories, media and metadata. The
private checkpoint receipt is scoped to the compiled batch and destination
pair, and retains a checkpoint after the ERP transaction and after each Woo
product. In the event of a partial result, preserve the receipt and
rerun the identical command to reconcile; never delete/restage the
products to restart.

First inspect without destination product writes:

```sh
sudo python3 "$HOME/RootedOps-commerce-pr57/scripts/commerce_production_draft_import.py" \
  --repo-root "$HOME/RootedOps" \
  --compiled "$HOME/commerce-migration/pilot-batches-1/pilot-01.json" \
  --sha256 ed49bd43b49cb9f705bd780f5f8d2220bd7aec32b2e4cc17c7dbde1a53f389d6 \
  --receipt "$HOME/commerce-migration/media-preparation-1/pilot-01-import-receipt.json"
```

Before authorizing a live product write, verify current backup/restore
coverage for ERPNext and WordPress, confirm new CI checks pass and visually
review the five source products. The same exact command with `--apply`
performs the guarded five-product import. Do not execute the provisional
`commerce_production_staging_batch.py --apply` runner. This new runner
does not support batches 2-5 or disabled-source imports; those require a
separate follow-up approval after complete first-batch reconciliation.

## Independent five-product reconciliation after import

After the first five-product import returns `erp_committed: true` and
`woo_receipted: 5`, reconcile **without writing any destination records**:

```sh
sudo python3 "$HOME/RootedOps-commerce-pr57/scripts/commerce_verify_production_pilot.py" \
  --repo-root "$HOME/RootedOps" \
  --compiled "$HOME/commerce-migration/pilot-batches-1/pilot-01.json" \
  --sha256 ed49bd43b49cb9f705bd780f5f8d2220bd7aec32b2e4cc17c7dbde1a53f389d6 \
  --receipt "$HOME/commerce-migration/media-preparation-1/pilot-01-import-receipt.json"
```

Expected: five ERP Items, Contents, Mappings and Prices, five Woo drafts,
zero Woo published products, no Sales Orders, Sales Invoices, Payment
Entries, Stock Entries or Bins, all source payloads/gallery/prices reconciled,
and `receipt_matches: true`, `reconciliation: PASSED`, `writes: false`.
This stricter 5/0 count gate is specific to the first pilot and **must not be
reused blindly after other sales, orders or inventory operations begin**.
If it fails, stop and investigate; preserve both media and import receipts.

## Remaining reviewed pilot batches (2–5)

After successful independent batch-1 reconciliation, the native product importer
accepts the remaining **four exact, previously compiled** batches. Their
immutable SHA-256 digests and exact Ecwid source IDs are allowlisted in
`scripts/commerce_production_draft_import.py`; the importer rejects
disabled-source products, foreign SKUs, missing receipt history, mismatched
media and unexpected price-list or tax policy. It does not fetch Ecwid or
republish products.

Batches must run **in order**, and each must pass its own installed
preflight and independent reconciliation before the next. The same private
receipt directory is used for all five batches, so successful earlier
receipts remain available:

```sh
cd "$HOME/RootedOps"
git fetch origin feature/commerce-full-catalog-staging-preflight
git -C "$HOME/RootedOps-commerce-pr57" checkout --detach \
  origin/feature/commerce-full-catalog-staging-preflight

BATCH=2
BATCH_LABEL="$(printf '%02d' "$BATCH")"
BATCH_FILE="$HOME/commerce-migration/pilot-batches-1/pilot-${BATCH_LABEL}.json"
BATCH_SHA="$(python3 - "$HOME/commerce-migration/pilot-batches-1/batch-index.json" "$BATCH" <<'PY'
import json,sys
index=json.load(open(sys.argv[1]))
matches=[x for x in index if x['batch']==int(sys.argv[2])]
assert len(matches)==1
print(matches[0]['sha256'])
PY
)"
RECEIPT="$HOME/commerce-migration/media-preparation-1/pilot-${BATCH_LABEL}-import-receipt.json"

# Read-only native target inspection of the next cohort
sudo python3 "$HOME/RootedOps-commerce-pr57/scripts/commerce_production_batch_readiness.py" \
  --repo-root "$HOME/RootedOps" --compiled "$BATCH_FILE" --sha256 "$BATCH_SHA"

# New native importer guard: no writes without --apply
sudo python3 "$HOME/RootedOps-commerce-pr57/scripts/commerce_production_draft_import.py" \
  --repo-root "$HOME/RootedOps" --compiled "$BATCH_FILE" \
  --sha256 "$BATCH_SHA" --receipt "$RECEIPT"

# Following accepted backup, reviewed output and passing CI, append --apply
# to the same importer command; do not add --apply to readiness or verifier.

# After applying, independently reconcile before BATCH=3.
sudo python3 "$HOME/RootedOps-commerce-pr57/scripts/commerce_verify_production_pilot.py" \
  --repo-root "$HOME/RootedOps" --compiled "$BATCH_FILE" \
  --sha256 "$BATCH_SHA" --receipt "$RECEIPT"
```

Expected cumulative ERP Item / Content / Mapping / Price and Woo draft counts:
batch 2 = 10, batch 3 = 15, batch 4 = 20, batch 5 = 22.
Published Woo products must remain zero. Financial and stock document counts
must remain unchanged (zero at the established pilot baseline). Preserve
receipts and output on failures; never delete or reset products to retry.
The first five-product receipt is not rewritten by importing subsequent
batches. Only the 22 previously reviewed and media-verified products are in
scope here; classification of the other 110 records is a separate activity.

## Production-staging runner — guarded first cohort

- Existing `scripts/commerce_catalog_batch.py` remains test2-only. The new
  `scripts/commerce_production_staging_batch.py` reuses its transaction,
  identities, media, replay and receipt logic but targets the installed
  production ERPNext site and staging Woo instance. It refuses disabled-source
  records until separately reviewed and restricts each invocation to 1–5
  compiled records, drafts only. This path has NOT been executed on production.
- Production runner requires `$HOME/commerce-migration/private/wordpress-credentials.json`
  with a scoped staging WordPress application password. Keep it at mode 0600,
  and protect directory at mode 0700; never commit credentials.
- Before the first write, confirm ERP container compose project identity,
  site, back-office baseline, staging WordPress URL, Coming Soon, no published
  products, live tax setting, zero enabled gateways and zero active Woo webhooks.
  The current runner does not yet perform the complete production reconciliation
  needed for this gate: review it before granting `--apply`.
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

This PR provides preflight, source-status safeguards and a first-cohort guarded
staging adapter. It is NOT a complete 132-product importer: disabled products,
category reconciliation, production authentication/media provisioning and
backups still require operator approval. Do not execute --apply yet.
