# Initial WooCommerce draft-only inventory projection (2026-11-03)

**Scope:** 24 exact MP->ERP->Woo source/ownership mappings accepted; 24 unique
`(item_id,strain_id)` pools, zero aliases, 78 currently available units;
the only proposed draft Woo deltas were seven zero-to-positive product
quantities (Woo IDs 25,35,38,40,43,44,45). These are **point-in-time**
observations. Do not reimport the 132 existing products or enable public
Woo checkout.

## Dedicated staging REST key

WooCommerce's official REST API uses Basic authentication over HTTPS
(consumer key:consumer secret). Use a dedicated **read/write** staging
REST key; never use the production Rooted Psyche WordPress site. The
credentials are in the private host `.env`, never in Git, shell output,
browser URLs, command-line arguments or public acceptance logs.

The operator **must run** this on the RootedOps production host. This repo
cannot connect to that host or populate its `.env` remotely.

```sh
cd ~/RootedOps
git pull --ff-only origin main
# Assert private .env stays 0600 and MP_SYNC_WOO_ENABLED=false.
stat -Lc '%a %n' .env
python3 scripts/commerce_woo_provision_auth.py
```

This creates **one** WooCommerce REST key attached to the **only**
Woo-capable WordPress administrator, for `shop-test.danks.store` only,
and puts a `Basic ...` header into
`MP_SYNC_WOO_AUTHORIZATION` in the existing private `.env` (0600).
It refuses ambiguous administrators, existing dedicated keys, populated
auth or enabled scheduled Woo synchronization. It never prints secrets.
The created key is linked to a WordPress administrator and is **not**
limited to seven SKUs at the Woo authorization layer; the separate
application guards enforce this initial-write scope. Review and revoke the
key in WooCommerce > Settings > Advanced > REST API after cutover if unused.

If provision fails after Woo key creation but before `.env` update,
do not rerun key generation blindly: reconcile/revoke the named key in
Woo settings first. Existing `MP_SYNC_WOO_ENABLED=false` remains unchanged.

## Guarded initial stock write

Take a fresh MushroomProcess and WordPress DB backup before the first
write; preserve the 2026-11-03 private crosswalk receipt
`~/commerce-migration/inventory-private/woo-stock-comparison-24.csv`.
Use fresh MushroomProcess `mp_commerce_inventory()` readings; do not trust
the earlier 78-unit snapshot as current. The proposal compares Woo
REST GET live identity, stock, metadata, draft/hidden status and exact
pre-existing Woo IDs. A changed set other than the seven approved IDs,
a different initial stock value, or any source drift refuses.
The initial source has no monotonic revision token; the script is *not*
a recurrence-safe production sync engine.

```sh
cd ~/RootedOps
umask 077
python3 scripts/commerce_woo_initial_stock.py \
  --mode plan \
  --file "$HOME/commerce-migration/inventory-private/woo-initial-plan-20261103.json"
```

Review printed quantities and the plan digest. Only after source
and target have been accepted, run with the exact printed digest:

```sh
python3 scripts/commerce_woo_initial_stock.py \
  --mode apply \
  --file "$HOME/commerce-migration/inventory-private/woo-initial-plan-20261103.json" \
  --approve EXACT_DIGEST_FROM_PLAN
```

Before the first write the script rereads all 24 MP listings and all
24 Woo product identities/quantities. MP source must hash identically
to the approved plan and every Woo row must still match the expected
previous value. Only stock_quantity of the seven approved **hidden draft**
products is eligible for PUT. Each attempt and read-back is appended with
`fsync` to an exclusively created private journal. On partial failure,
STOP: do not blindly rerun the plan; inspect the journal and target
stock then reconcile manually. It confirms all 24 final quantities.

**Do not** turn on `MP_SYNC_WOO_ENABLED` after this one-time write.
Durable source revision/high-watermark, destination acknowledgement
lifecycle, duplicate/out-of-order control, failed-write retries, live
Ecwid parity and checkout/reservation admission must be accepted before
recurring Woo quantity projection or public checkout. The one-time tool
does not modify Ecwid, ERPNext operational read-model or ERP stock ledger.
