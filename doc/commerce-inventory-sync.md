# MushroomProcess inventory projections (2026-11-03)

## Authority and current cutover status

MushroomProcess is **the only operational sellable-availability authority**.
Its PostgreSQL Product/Lot rules remove expired, consumed, shipped, composted,
retired and missing products even when there was no website order. The shared
order ledger (MP migrations 052/054) subtracts active reservations separately,
so two channels cannot treat one available unit as two independent units.

ERPNext owns Item identity, commercial content, Item Prices and accounting.
WooCommerce is a storefront projection. **Do not** create ERP Stock Entries,
stock valuation or Bin adjustments merely to mirror MP. The new ERP
`Commerce Operational Availability` DocType is a separate read-only read
model with one record per reviewed MP ecommerce ID, shown on the Item screen.
It is not the sum of all variants/mappings for an Item.

The merged replacement n8n file is in MushroomProcess at
`n8n/workflows/MushroomProcess - Commercial Inventory Sync - PGSQL.json`.
It preserves the original Ecwid SKU search, quantity/UPC PUT and PostgreSQL
writeback, and adds the manual Commercial Catalog Snapshot's reservation-
adjusted query and link validation. It imports **inactive**. The original
Ecwid workflow remains in Git as an operational rollback.

## Independent switches

RootedOps Compose passes these values from private `.env` to n8n:

| Variable | Default | Function |
| --- | --- | --- |
| `MP_SYNC_ECWID_ENABLED` | `true` | Preserve working Ecwid quantity/UPC sync |
| `MP_SYNC_ERP_ENABLED` | `false` | Write per-ID availability to ERP read model |
| `MP_SYNC_WOO_ENABLED` | `false` | Update existing *hidden drafts* at exact `shop-test.danks.store` only |
| `MP_SYNC_ERP_BASE_URL` | `http://erpnext-backend:8000` | Internal Frappe endpoint |
| `MP_SYNC_ERP_AUTHORIZATION` | blank | Private Frappe token authorization header |
| `MP_SYNC_WOO_BASE_URL` | blank | Must equal `https://shop-test.danks.store` |
| `MP_SYNC_WOO_AUTHORIZATION` | blank | Scoped Woo API authorization header |

Blank authorization is intentional. Store credentials in private host `.env`
only, not Git, commits, workflow JSON or evidence. Before enabling any new
destination, explicitly verify its credentials and private network reachability.

ERP Frappe site gate is separately **disabled**:
`mp_inventory_erp_projection_enabled` must explicitly be enabled after
reviewed MP Item-to-ERP channel mapping and authenticated role acceptance.
The API refuses missing/stale/ambiguous MP identities, negative/fractional
quantities and mismatching provider/site. It has no Stock Ledger side effects.
The ERP Item Desk displays per-MP ecommerce ID quantities read-only.

Woo's initial adapter is intentionally **draft-only**, simple products, no
variations and no publication. Each selected row must have exactly one enabled
Woo `Commerce Channel Mapping` whose provider/site/item/SKU/MP ecommerce
ID/Woo product ID match, and the Woo record must be hidden, draft,
`manage_stock=true`, with matching `_rootedops_source_key`. It sends only
`stock_quantity` and checks the response. It does not create or enable
storefront products, prices, discounts, images or tax configurations.

**Mapping blocker:** Importing 132 Ecwid products and reconciling ERP descriptions
does not prove that 132 MP ecommerce IDs have been reviewed or linked. Likewise,
119 approved tax-classified sellable SKUs do **not** establish 119 approved
inventory mappings. Missing mapping causes refusal, not guessed SKU matching.
The excluded 13 generic POS identities must stay blocked.

## Safe cutover of n8n workflow

Do not import both as hourly-active workflows. Work on existing production n8n;
**test2 has been stopped with its databases and volumes retained**.

1. Archive the currently active Ecwid n8n workflow, its exact version,
   credentials *references*, current execution ID and the MP database schema
   version. Do not export secret values in public evidence.
2. Import the new generic workflow as **inactive**, bind the existing
   production PostgreSQL credential (Ecwid branch reuses current reference).
   Keep `MP_SYNC_ERP_ENABLED=false`, `MP_SYNC_WOO_ENABLED=false`,
   `MP_SYNC_ECWID_ENABLED=true`.
3. Run Node regression `node n8n/tests/commercial_inventory_sync_smoke.js`;
   compare original and new Ecwid node definitions/quantity candidates.
4. Avoid a parallel paid/scheduled execution: stop the old Ecwid hourly schedule
   **at the handoff**, then activate the new hourly workflow. Perform one
   manual execution; Ecwid should be the only destination modified, and
   PostgreSQL metadata writeback should match historical behavior. Observe
   logs/status for an hourly period before regarding it as accepted.
5. Compare current MP physical Product/Lot counts, reserved amounts and
   resulting Ecwid quantity, including an eligible unit moved to Consumed or
   allowed to expire **without an order**. Recheck after hourly run. Review
   differences before enabling additional providers.
6. Review ERP MP ecommerce identity links and distinct Woo product mappings.
   Enable ERP independently, then Woo independently, only with a separately
   approved host configuration change and controlled n8n service refresh.
7. Verify stale/same-timestamp ERP snapshot refusal, isolated Woo draft
   update and read-back, reservation decreases, physical decreases, no duplicate
   writes and failures/retries before any real Woo publication.

**Unresolved cutover gate:** This first draft-only Woo adapter has no durable
out-of-order delivery lock or cross-run completion ledger; it is not approved
to update published products or to synchronize inventory while both Ecwid
and Woo independently accept customer orders. The production stock writer
needs persisted versioned acknowledgments, retry/error reporting and an
atomic MP reservation admission gate before final Ecwid cutover.

## Versioning and rollback

The old workflow JSON remains in the repository and can be reactivated
after stopping the generic replacement. Do not run both hourly workflows.
If ERP/Woo validation fails, leave those switches false; Ecwid sync can
continue unchanged. No test2 ERP restart, new clean Linode, or reimport of
132 catalog records is necessary.

Related: RootedOps #2/#20; MushroomProcess #80/#85/#86.
