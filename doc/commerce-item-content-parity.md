# ERPNext authoritative catalog content parity — November 3, 2026

## Evidence and scope

Owner read-only native inventory on `erp.danks.store` found **132 Item records and
132 Commercial Product Content records**, with exactly one joined content record
per Item. Every inspected Item description was empty while the corresponding
commerce full description and both SEO fields were populated. Item names and
public titles matched in the printed results. This is a native **Item projection**
gap, not missing commerce app data or a reason to reimport Ecwid.

The **authoritative editorial record** remains `Commercial Product Content`:
`public_title`, `short_description`, `full_description`, `seo_title`,
`seo_description` and gallery. Native Item owns accounting identity and standard
ERP representations; `Item Price` owns prices. MushroomProcess owns availability,
reservations and fulfillment. WooCommerce and future channels receive projections,
not independently authored canonical product content.

## What this change does

- New imports seed `Item.description` from reviewed authoritative
  `content.full_description`; existing Item records are not overwritten by importer
  replay.
- New `rootedops_commerce.catalog_sync.reconcile` provides a **read-only default**
  inventory/digest of native description changes. `apply` requires the exact
  read-only digest and the caller's expected Item/content/join count. It refuses
  missing/mismatching public titles and any nonempty divergent native description.
  It only fills blank native `Item.description` values from content.
- No changes to Item tax templates, groups, stock, valuations, prices, publication
  flags, galleries, WooCommerce records, payroll, financial documents or channel
  mappings. No new Ecwid import is needed.
- SEO remains in `Commercial Product Content`, not duplicated into hypothetical
  native ERPNext webshop fields. The existing WooCommerce SEO adapter continues
  to consume those canonical fields.
- This first repair is an explicitly operator-approved *backfill*, not a new
  automatic edit hook. Future changes to canonical commercial content require a
  separate guarded editorial publishing/sync workflow. Do not author product
  descriptions directly on Item expecting reverse synchronization.

## Operator acceptance (only after PR review/merge)

Confirm `./erpnext/deploy.sh commerce` finishes and verify commerce imports on
the running backend. This does not replace a separate persistence-image rebuild.

Run from the production host:

```bash
cd ~/RootedOps
git pull --ff-only origin main
./erpnext/deploy.sh commerce

# Read-only: captures the exact current source + native Item state.
sudo docker exec erpnext-backend \
  bench --site erp.danks.store execute rootedops_commerce.catalog_sync.reconcile
```

Expect `item_count=132`, `content_count=132`, `matched=132`,
`updates_needed=132`, `conflicts=[]`, `writes=false`. Do not proceed if these
expectations or the source provenance differ.

Review and explicitly approve the printed digest. Only then:

```bash
sudo docker exec erpnext-backend \
  bench --site erp.danks.store execute rootedops_commerce.catalog_sync.reconcile \
  --kwargs '{"apply": true, "approve_digest": "PASTE_THE_REVIEWED_64_CHAR_DIGEST", "expected_count": 132}'

# Verify a second read-only run reports zero pending changes.
sudo docker exec erpnext-backend \
  bench --site erp.danks.store execute rootedops_commerce.catalog_sync.reconcile
```

`apply` commits only after all native Item writes and protected record-count
checks succeed. On failure the transaction rolls back. **Do not execute an
unreviewed raw SQL UPDATE**, do not alter the 13 blocked generic POS identities'
checkout eligibility, and do not republish Woo products.

## Docker image persistence remains a separate gate

Owner's existing running `erpnext-backend` imports
`rootedops_commerce 0.3.1` from the mounted shared `erpnext_apps` volume.
A fresh container from the image `rootedops-erpnext:version-16` did not
import commerce. RootedOps compose mounts the shared app volume over the app
tree and the Dockerfile already installs both modules. **This does not establish
a missing site install**. It establishes that the current image should not be
relied upon for clean recovery until rebuilt and separately verified.

Build a *candidate with a distinct tag*, rather than overwriting a running
image tag or recreating production containers:

```bash
cd ~/RootedOps
# Confirm configured base tag/branches in .env privately.
# Replace values below with actual .env values if different.
sudo docker build -f docker/erpnext-custom.Dockerfile \
  --build-arg ERPNEXT_IMAGE_TAG=version-16 \
  --build-arg ERPNEXT_HRMS_BRANCH=version-16 \
  --build-arg ERPNEXT_ESS_BRANCH=version-16 \
  -t rootedops-erpnext:commerce-candidate .
sudo docker run --rm \
  --entrypoint /home/frappe/frappe-bench/env/bin/python \
  rootedops-erpnext:commerce-candidate \
  -c 'import rootedops_payroll, rootedops_commerce; print("Both imports OK")'
```

A passed candidate import check is **not** authorization to replace the
production image. Verify the versioned app wheel/editable install and a
fresh-container restore rehearsal; promote in a separate controlled rollout
with backup and rollback. Do not prune or delete `erpnext_apps`.

## Still open for cutover

Native destination-aware taxes and Woo checkout parity; live authenticated Woo
webhooks through isolated n8n/MushroomProcess/ERP; Clover sandbox and payment
reconciliation; the approval-based ERP-to-Woo editorial projection, and verified
MushroomProcess inventory/fulfillment synchronization. All existing 132 catalog
records and Woo draft product identities should remain untouched during this
native description backfill.
