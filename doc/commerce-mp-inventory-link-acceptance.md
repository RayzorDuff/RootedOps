# MP -> ERP reverse-link and inventory projection acceptance (2026-11-03)

## Precondition and scope

The operator applied MP PostgreSQL migration 051/052 and committed the independently
reviewed 24-row `ecommerce.erp_item_code` crosswalk on production; MP read-back
returned 24/24 mapped rows. The ERP side still has 132 Ecwid Commerce Channel
Mappings with `provider=ecwid`, `site_key=95802503` and `sync_enabled=0`.
MP uses `site_key=dank_mushrooms`; those two site keys are deliberately
different and **must not** be normalized across databases. The approved crosswalk
matches **both** exact SKU/ERP Item code and Ecwid product ID for every row.

This change affects only the ERP `Commerce Channel Mapping.mushroomprocess_ecommerce_id`
reverse link. No Item/catalog rebuild, changed Ecwid provider identity, quantity,
price/tax, Woo product, reservation, or sync activation is authorized.
Existing production ERPNext may run commerce 0.3.2 while main has newer code;
the script is a one-off Frappe-console operator helper, not an app deployment.

## Operator preview and guarded write

Take a fresh **ERPNext MariaDB database backup** first and preserve the existing
MP PostgreSQL mapping backup. Review the approved 24-row CSV and the two noted
catalog description differences (especially MP 7.5lb versus ERP 5lb Master's Mix
on ID 31); do not silently change descriptions or sellable weights.

On the production host, after this PR is merged to main and pulled:

```sh
cd ~/RootedOps
git pull --ff-only origin main
sudo docker cp scripts/commerce_mp_reverse_link.py erpnext-backend:/tmp/commerce_mp_reverse_link.py
# PREVIEW: never writes
printf '%s\n' "ns = {}; exec(compile(open('/tmp/commerce_mp_reverse_link.py').read(), '/tmp/commerce_mp_reverse_link.py', 'exec'), ns); ns['run_backfill'](frappe, apply=False)" "exit()" | sudo docker exec -i erpnext-backend bench --site erp.danks.store console
# APPLY: only after 24/24 preview, fresh backup and operator acceptance
printf '%s\n' "ns = {}; exec(compile(open('/tmp/commerce_mp_reverse_link.py').read(), '/tmp/commerce_mp_reverse_link.py', 'exec'), ns); ns['run_backfill'](frappe, apply=True)" "exit()" | sudo docker exec -i erpnext-backend bench --site erp.danks.store console
```

The script asserts exact 132 existing mapping count, correct ERP site, 24 exact
provider/site/SKU/Item/Ecwid IDs, no duplicate MP ID, no unrelated MP ID link,
empty variation IDs, and every target `sync_enabled=0`. It accepts
already-correct reverse links for idempotent replay, locks mappings for
a write, validates full post-write identity fields and rolls back on failure.
Use read-back confirmation before calling it complete. Do **not** update ERPNext
stock Bin/Stock Ledger or Item Price from MP operational counts.

## Read-only projection readiness

From the same production host, run
`scripts/commerce_mp_inventory_readonly.sql` against the MP bridge PostgreSQL:

```sh
sudo docker exec -i mushroomprocess-bridge-postgres sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" exec psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < scripts/commerce_mp_inventory_readonly.sql
```

The summary should return 24 inventory rows, 24 ERP links and 24 availability
values within [0, physical quantity]. The detailed rows use the
reservation-adjusted `mp_commerce_inventory()` value rather than only the
physical `desired_quantity`. A clean snapshot is **not** permission to
publish or push Woo stock.

Next reconcile actual 24 source rows against the ERP reverse-link read-back,
the reviewed existing Woo draft SKU/ID ownership map, and the live Ecwid
published quantity. Do not infer an MP->Woo identity from matching SKU alone.
Store a durable source snapshot/revision/hash and independent destination
acknowledgments with stale/replay refusal, then test only an explicitly approved
draft/non-sellable Woo item in an isolated environment. Existing
`integrations/commerce/sync.py --apply-staging` can upsert draft products and
stock; **do not use it as an inventory-only writer**. The separate editorial
projection explicitly excludes inventory. ERPNext should receive operational
visibility, not manufactured Stock Ledger Entry or stock valuation adjustments.

Until checkout cross-channel reservation, idempotent delivery, duplicate,
cancellation, partial-shipment and outbound failure acceptance is complete,
keep Ecwid's hourly stock workflow active, and keep ERP/Woo inventory writers
disabled. Avoid promoting Woo to public checkout while both stores could
reserve the same physical stock independently.
