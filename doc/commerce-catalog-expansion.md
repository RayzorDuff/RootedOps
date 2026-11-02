# Real catalog expansion checkpoint

**Superseded by installed execution:** all nineteen candidates subsequently
imported. See [commerce-catalog-expanded-test2.md](commerce-catalog-expanded-test2.md)
for 22-product acceptance, completed galleries and command-scoped lock usage.
The blocked/prepared checkpoint below is historical evidence.

Continuation baseline: RootedOps main `a6f8d447893ec548981b3c75b429ed2dcb31f471`
(merged #52). MushroomProcess main inspected at
`451393c621b64c5bd4ca7d03b1525c6253f641ae`; no MP changes.

## Installed versus prepared

**No additional installed imports in this checkpoint.** Three exclusive Commerce
lock attempts returned `Console is reserved by another session.` A fourth attempt
after the reconciliation checkpoint returned the same refusal. No server
operations followed a refusal; no lock was acquired, bypassed or removed.
The visible console was in a SignatureGate checkout, but the lock command did not
identify its holder. Do not infer abandonment or terminate that session.

The last verified installed state remains [#52's evidence](commerce-pilot-pricing.md):
three ERP/Woo products, three reconciled USD prices, stable IDs, draft/hidden,
zero managed stock. Galleries remain one imported primary per product; seven
original pilot image URLs are archived but not applied. Taxes and installed order
flow remain open; Clover remains separate. Production/Ecwid were untouched.

Distinguish the source and destination identifiers:

| Ecwid product ID | ERP Item Price ID | Woo product ID |
| --- | --- | --- |
| 610274980 | 51dh7jssbr | 18 |
| 610274742 | 51dd36tc1u | 20 |
| 711334880 | 51e8nrhi2a | 22 |

## Original source reconciliation

The actual original `products_2026-10-29_03-23 (1).csv` was downloaded and read;
SHA-256 matches `347660a5c4ccf3d434a8beda02c63e2d137871224d2ddfbf85f8e84b27f9d2bf`.
Its immutable identities/categories independently reproduce the nineteen-candidate
scope. The generated report is private; full source rows are not committed.

| Coverage | Products | Handling |
| --- | ---: | --- |
| Last installed ERP/Woo acceptance | 3 | Preserve pilot identities; not reverified here |
| Additional category-appropriate candidates | 19 | Pending real imports |
| Enabled in Disabled category | 12 | Hold for owner classification; generic dollar-value products, including NOTAX labels |
| Enabled, uncategorized | 4 | Hold for category review; actual products, not discarded |
| Disabled original records | 94 | Preserve original IDs/SKUs/history; no sellable recreation |
| Total enabled / total original | 38 / 132 | No claim of complete catalog migration |

Uncategorized records: `711333863` (2.5lb Master's Mix), `711335072` (2lb WBS),
`711334876` (Chestnut LC), `711335074` (Turkey Tail LC).
Four additional candidates lack a CSV image: `711335071`, `711334877`,
`711335795`, `753212607`. This is a source gap, not a failed download.
The API snapshot must still be compared before destination writes; source price
or SKU changes block that candidate instead of overwriting the original CSV.

| Prepared batch | Actual Ecwid IDs (not imported) |
| --- | --- |
| 1 | 711335071, 711334877, 711335795, 753212607, 610274979 |
| 2 | 610277364, 828374466, 828374469, 829845573, 711335076 |
| 3 | 711335075, 711335798, 711335797, 610276912, 610274451 |
| 4 | 610276905, 610277365, 610276670, 610276199 |

Prior API evidence reports no enabled options/combinations and three empty pilot
combination endpoint responses. No new API variation checks ran here. The CSV
cannot prove absence of variants; the coverage helper preserves unknown separately
from verified empty. Public disabled placeholders must not replace full CSV data.
Tax labels `default`, `zero`, and NOTAX names do not establish tax rates/exemptions.
No new tax mapping was guessed or activated.

## Continue using the existing importer

`catalog_coverage.py` reconciles original CSV records with optional later API
records and installed per-product read-back receipts. A receipt must contain
`ecwid_product_id`, exact `erp_item`, `woo_id`, and `installed_verified=true`.
Pass only fully verified ERP+Woo product receipts, not ERP-only partial entries.
Without receipts its report deliberately counts all enabled records as pending;
the three-product predecessor acceptance above remains separate evidence.

```bash
python3 integrations/commerce/catalog_coverage.py /private/products.csv \
  --api-products /private/api-products-array.json \
  --verified /private/installed-products-array.json \
  --output /private/catalog-coverage.json
```

`scripts/commerce_catalog_batch.py` executes existing `migrate_reviewed.py`
compiled output (at most five verified simple products), with existing
`rootedops_commerce.api.import_product`, `catalog`, and `channel.upsert_draft`.
It introduces no alternate source conversion or product persistence mechanism.
Use the existing media archiver/uploader and checksum reconciliation **first**;
the runner accepts uploaded attachment IDs and ERP Files, never remote image URLs.
The existing compiler still requires reviewed category, price-list/UOM/group and
tax mappings; this checkpoint does not supply missing tax policy.

After acquiring the lock and attaching only Commerce Screen:

```bash
# Compile the selected source identities with the existing reviewed compiler.
python3 integrations/commerce/migrate_reviewed.py catalog \
  /private/catalog-plan.json /private/catalog-review.json \
  --source-key ecwid:95802503:product:711335071 \
  --media-manifest /private/uploaded-media.json \
  --output /private/batch-reviewed.json

# Inspect the compiled file, then use its exact SHA for both invocations.
sha256sum /private/batch-reviewed.json
sudo -n python3 scripts/commerce_catalog_batch.py \
  /home/rootedops/RootedOps/.test-deployment /private/batch-reviewed.json \
  --sha256 REVIEWED_COMPILED_FILE_SHA256
sudo -n python3 scripts/commerce_catalog_batch.py \
  /home/rootedops/RootedOps/.test-deployment /private/batch-reviewed.json \
  --sha256 REVIEWED_COMPILED_FILE_SHA256 --apply
```

Those are reproducible command templates, **not executed installed commands**.
Use absolute script paths from the reviewed checkout if host main is older.
Do not overwrite a concurrently used checkout or rebuild shared services.

Preflight checks exact Test2 targets, internal container networks, live WordPress
mail/HTTP/cron/payment controls, zero active Woo webhooks, source/SKU/USD identities,
uploaded media and existing draft ownership. Apply imports each ERP record twice
inside a transaction, compares counts/IDs/content/prices, and preserves financial,
stock and File counts. Woo upsert runs twice and reads authenticated edit context;
it verifies IDs, descriptions, SEO metadata, categories, prices, ordered image IDs,
draft/hidden/zero-stock/backorder state. No media uploads occur in this runner.

Private receipts under `.test-deployment/private/catalog-batches/` retain an ERP
checkpoint before Woo writes, incremental verified products and pending Woo IDs.
If ERP commits and Woo later fails, inspect that receipt and exact SKU ownership,
correct the specific mismatch and replay the same reviewed batch. Do not restore,
reset or recreate successful products. Variable families are refused before
destination access and must use their existing reviewed variation path with
separate installed acceptance; do not flatten them into simple products.

Validation here: six new targeted offline tests pass; no predecessor native
database suite rerun. Native batch body, live shop guard, media parity and the
nineteen real destination writes remain **unexecuted** pending console access and
actual reviewed input. These tests are not installed acceptance evidence.
