# Commerce cutover continuation without test2 (2026-11-03)

## Accepted state

- Production ERPNext `erp.danks.store` runs `rootedops_commerce` 0.3.3 after
  the owner merged PRs #72/#73/#74 to main. The previously accepted backfill
  applied 132 descriptions and the independent reconciliation showed zero drift.
  **This does not establish that the latest UI/browser edits or outbound sync
  have been exercised on the live site.**
- Production staging Woo at `shop-test.danks.store` has the accepted 132
  Ecwid-source draft product identities; 119 reviewed sellable classifications
  and 13 generic POS exclusions. Do not reimport/recreate the catalog.
- On production host, owner successfully built
  `rootedops-erpnext:review-1b1e0257a67d` with image ID
  `sha256:0757035aa9f7c4d5977509ddf0fe67b06db2720a9b096577770f8ad29056558d`.
  Fresh no-volume/no-network imports passed for payroll 0.4.10 and commerce 0.3.3.
  This build is **not** an ERPNext service/container and needs no shutdown.
  The live `rootedops-erpnext:version-16` image is still the older deployment
  until a separately authorized controlled promotion.
- Ecwid remains the live order/inventory publication destination until cutover.

## Actual inventory paths (do not overclaim readiness)

Existing production **MushroomProcess - Ecwid Catalog Sync - PGSQL** n8n
workflow (hourly per MP documentation) consumes
`mp_ecommerce_ecwid_catalog_sync_candidates()`, matches exact Ecwid SKU,
PUTs quantity/UPC, then calls
`mp_ecommerce_ecwid_catalog_sync_writeback()`.

Provider-neutral migration 051 adds `ecommerce.erp_item_code` and
`mp_ecommerce_catalog_inventory()`. Migration 052 adds a shared provider-
neutral order/reservation ledger and `mp_commerce_inventory()` that subtracts
reservations; 054 adds confirmed reservations/partial-shipment acknowledgments.
The **MushroomProcess - Commercial Catalog Snapshot - PGSQL** export contains
a manual trigger, Postgres inventory query joining these functions and
mapping validation only. It has no active output writer to ERP/Woo/Moov.

RootedOps `integrations/commerce/sync.py` can create a *staging draft*
projection using an MP snapshot and ERP-authenticated content, optionally
including Woo stock quantity. It is a CLI with reviewed mappings and
`--apply-staging`, not an automatically active n8n multi-destination writer.
`integrations/commerce/editorial_projection.py` from PR #74 intentionally
updates only content/SEO and explicitly does not touch inventory.

**Proposed fanout:**
MushroomProcess physical Product/Lot eligibility and cross-channel confirmed
reservation ledger -> durable versioned availability snapshot
(`ecommerce_id`, ERP Item, provider/site/product/variation identity,
quantity, observed/revision, source hash, error status) -> independent
idempotent destination adapters for WooCommerce managed stock and ERPNext
availability visibility; future Moov after confirming an actual supported
inventory API. ERPNext must not calculate/resend inventory as another
authority or create native stock ledger movements merely because MP stock
changed. Keep ERP accounting/stock valuation distinct until designed and
accepted. Mixed aliases must not double-count or oversell the same units.

Before activating Woo inventory writes: review exact MP ecommerce-to-ERP and
Woo crosswalk, distinguish 119 sellable/13 excluded POS items, lock down
source and target host, verify current quantity and reservations, compare
Ecwid published quantity versus new MP snapshot, implement out-of-order
revision protection and durable acknowledgment/retry, and prove single-item,
multiple SKU/lot, duplicate, cancellation, partial shipment and failure cases.
Do not enable both Ecwid and Woo checkout unless one reservation ledger
covers both channels in a verified way. Coordinate first stock push and
publication with live order intake handoff.

## Retire shared test2 compute without deleting the evidence

Run only on the **separate test2 Linode**, not on the live
`dankmushrooms@localhost` production host. First preserve the last test2
backup, app/version/image inventory, private acceptance receipts, restore
metadata, and the n8n/ERP encryption keys in their existing protected backup
location. Confirm no active SignatureGate or other users hold test2 resources;
the shared `rootedops-full-test` project includes services outside commerce.

```bash
cd ~/RootedOps
git pull --ff-only origin main
bash -n scripts/stop_shared_test2.sh
# Read-only preview; checks .test-deployment/TEST_ENVIRONMENT and Compose labels.
bash scripts/stop_shared_test2.sh
# Explicit stop after confirming private backups/other users:
bash scripts/stop_shared_test2.sh --stop --confirm-shared-test2
# Confirm neither shared project still runs.
sudo docker ps --filter label=com.docker.compose.project=rootedops-full-test
sudo docker ps --filter label=com.docker.compose.project=dank-store-test
```

The script stops **only** containers belonging to those exact two test2
Compose projects; it refuses a host without the test2 marker and labels.
It does **not** call `compose down`, delete a volume, prune an image, remove
backups or alter production. Unrelated test2 projects, separate scheduling
stacks, DNS records, reverse proxy and certificate renewals remain untouched
and must be inventoried independently before final Linode decommission.
If the project checkout/marker is unavailable, do not bypass the guard.

## Continue directly on installed production + staging shop

1. Preserve fresh private backups and inspect current ERP service/image IDs,
   `erpnext_apps` volume mounts and production app versions. The proven
   candidate image is available and there is no need to recreate test2.
2. Use a **controlled image promotion** with pinned candidate ID, a rollback
   image reference and a coordinated ERP application service restart.
   The separate apps volume masks image files; ensure committed 0.3.3 source
   in that volume after rollout. Do not run `docker compose down -v` or
   `docker volume rm`. A candidate import check is not a full restore test.
3. Run scoped ERP Desk acceptance against `erp.danks.store`: verify the Item
   Commerce section renders SEO/gallery, Sales Manager can edit a **reviewed
   disposable/non-sellable record** (not an existing approved live SKU), Sales
   User cannot, direct Item drift is refused and Woo remains unchanged. Do not
   activate storefront sync during UI testing.
4. Wire the independently reviewed ERP content adapter to existing
   `shop-test.danks.store` mapped draft products with source-key, Woo-ID,
   snapshot digest and read-back receipts, initially read-only.
5. Implement and verify MP-authoritative available-quantity fanout. Woo is
   managed stock; ERP receives availability for operational visibility,
   **not** ledger valuation. Keep Ecwid inventory sync active until a
   coordinated handover, then disable it at cutover.
6. Resume destination-aware tax parity, authenticated n8n order delivery and
   Clover sandbox authorization/capture/replay checks using private credentials.
   Never publish Woo/enable gateways or retire Ecwid until these pass.

This is a continuation plan, not evidence that test2 was stopped or the
live ERP image promoted. The operator must execute host-side commands.
