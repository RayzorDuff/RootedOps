# Remaining Ecwid product import — 110 draft records

The accepted production ERPNext / staging WooCommerce pilot from PR #57 already
imported and reconciled 22 products. **Do not repeat it.**

This importer continues from the immutable 132-product Ecwid store `95802503`
snapshot with SHA-256
`0b4eec40a1cfd1d62551e2ac951a42dac21984f34ffb2d03f9aea697d1d713a8`.

The operator's existing `~/commerce-migration/media-archive/` already contains
a source archive manifest with **147 image URLs / 41 unique binaries**. The
importer verifies these and downloads only source URLs actually needed by the
remaining 110 products that are not already archived. It reuses the 11-image
pilot upload receipt and uploads any additional unique image binaries natively
to production ERPNext Files and staging WordPress attachments.

## Scope

- **110** previously unimported Ecwid source products: 16 enabled, 94 disabled.
- Preserves original source-enabled status as WooCommerce metadata.
- All destination Woo products remain `draft`, `hidden`, zero-quantity,
  `outofstock`, no backorders, no enabled checkout.
- No product stock operations; ERPNext Items are non-stock, and catalog mappings
  remain `sync_enabled=0`.
- Missing source image = empty gallery, not a fabricated placeholder.
- Missing source price = no ERPNext Item Price and blank Woo regular price, not
  an invented zero-dollar offer.
- Unknown Ecwid category or no category = existing Woo **default product
  category**, with original Ecwid category IDs retained in metadata and
  complete original source payload in ERP. No invented retail department.
- Product taxonomy, tax rules, publishing and inventory remain separately
  reviewed launch tasks.
- No additional source export, test2 rehearsal, test environment or five-product
  operator batches.

## One-command workflow

Once this PR is merged and `~/RootedOps` has been fast-forwarded to the new
`main` commit, ensure current backup/restore coverage for the production
ERPNext database and staging WooCommerce installation. Then run a concise
read-only count of the remaining source and archived image URLs:

```sh
cd "$HOME/RootedOps"
python3 scripts/commerce_remaining_catalog.py \
  --repo-root "$HOME/RootedOps" \
  --source "$HOME/commerce-migration/ecwid-full-catalog-source.json" \
  --archive "$HOME/commerce-migration/media-archive" \
  --state-dir "$HOME/commerce-migration/remaining-110"
```

To download missing required source images, upload additional media, import all
110 draft products, automatically replay to verify destination identity, and
perform one final independent reconciliation in **one command**, repeat with
`sudo` and `--apply`:

```sh
sudo python3 "$HOME/RootedOps/scripts/commerce_remaining_catalog.py" \
  --repo-root "$HOME/RootedOps" \
  --source "$HOME/commerce-migration/ecwid-full-catalog-source.json" \
  --archive "$HOME/commerce-migration/media-archive" \
  --state-dir "$HOME/commerce-migration/remaining-110" \
  --apply
```

If a needed image host was not among the explicit hosts in the previously
reviewed archive, the command stops before fetching it. Review the original
source URL and rerun adding `--allow-host approved.example.com` for that
particular approved origin. Do not disable host or HTTPS validation.

There is no need to stage media URLs for all missing thumbnail variants. Only
source URLs used as a primary/gallery image for the remaining products are
downloaded. Existing source-free products are retained as source-free.

## Recovery and completion

The operator retains these private `0600` receipts below
`~/commerce-migration/remaining-110/`:

- `new-media-urls.json`: only newly downloaded image URL/hash records.
- `remaining-media-receipt.json`: per-blob File/attachment destinations.
- `remaining-product-receipt.json`: completed ERP chunk identities and every
  Woo product ID; each write is replay-safe.
- `remaining-final-report.json`: final count and read-back reconciliation.

The original 147-URL archive manifest, pilot receipts and product batch files
are **not overwritten or deleted**. Failed or interrupted imports must be
resumed with the same command and same private state directory. Never reset the
production ERPNext catalog or delete partially imported products.

Success requires 132 ERPNext Items, 132 Commercial Product Content records,
132 Commerce Channel Mappings and **132 unpublished WooCommerce drafts**.
Price counts can be lower if any original product has no price. Existing
financial/stock transaction counts must remain zero at this pre-launch
baseline. The final report returns `status: PASSED`,
`remaining_checked: 110`, `receipt_matches: true`, and zero published products.

After completion, return to native ERPNext taxes, installed order flow and
Clover sandbox integration. **Do not retire Ecwid or activate Woo checkout
based on catalog import success alone.**
