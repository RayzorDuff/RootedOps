# Woo stock after the Ecwid inventory correction

Merged MP #118 introduced a shared physical specification pool. Existing Ecwid listings generally retain its publication ownership while Ecwid checkout remains live. Woo publication must not turn the nonowner's intentional zero availability into an opening stock update. The publisher now requires `mp_inventory_specs().is_owner=true` and deduplicates by that pool key, preserving distinct size/stage pools that use the same legacy Item/strain. It retains Woo's existing reservation/native-deduction handling and exact product/variation/SKU/source-key checks.

The paired MP follow-up 059 makes the same eligible generic-item Product or whole Lot count, reserve, pick and dispatch consistently. Existing Ecwid order fulfillment, its stock baseline and receipts remain intact. Installing 059 does not change publication ownership. Keep every Woo write gate disabled until the installed prerequisites and restricted owner-order acceptance pass.

## Installed evidence carried forward

The operator applied MP 058 successfully. Coco's first live delta +4 was acknowledged as applied after finite-stock readback 4; the product was re-enabled and the sale remained pending. A manual revised Commercial Inventory Sync run reported ecommerce 1 `unchanged`, other 23 mappings `review_baseline_required`, and no errors. The owner enabled the revised schedule and archived the legacy Ecwid sync. Two sale lots have since been packaged into Products in MP; cash payment is possible and unconfirmed. The owner confirmed there is no Ecwid order for those two Products and none is expected for a cash sale. Packaging is not dispatch and must avoid counting the origin Lot twice. A direct MP cash-sale dispatch reduces stock through one inventory delta; preserve the unrelated earlier hold. This does not approve new baselines for the other products, prove a completed sale/fulfillment or establish deployment of the Woo stack.

Current supplied hostname evidence: both shop-test and dankmushrooms.net serve the same WP backend at 8097 with TLS. Only shop-test had the customer route to 8100; the order receiver at 8102 was absent. WP home/siteurl were still shop-test. Production ERP commerce was last reported as 0.3.4. These installed versions/routes must be checked again before changing them; passing CI is disposable evidence.

## Merge/deploy order

Preserve RootedOps's existing order stack #111 → #112 → #113 → #115 → #116 → #118 → #119 → #120 → #124, then this follow-up. #117 is the independent storefront runbook; #114 settlement/funding is a separate review stream. MP #115 → #116 → #117 → shared-pool follow-up 059 carries merged main/#118 inventory into those branches. Their updated CI tests both the standalone Ecwid correction and combined Woo fulfillment.

Use [MP's exact schema/owner procedure](https://github.com/RayzorDuff/MushroomProcess/blob/feature/commerce-shared-pool-fulfillment/doc/commerce-shared-pool-cutover.md). On this Linode 058 is already installed. After backups and the actual schema preflight, apply the missing 054/055/056/057 prerequisites, then 059; do not rerun 058 or bulk-apply old migrations. Stop on partial installations or unrecognized definitions. Deploy commerce app 0.3.6 from the reviewed RootedOps image through the existing production ERP procedure; no new bench is required.

## Hosted acceptance and hostname

Use [dankmushrooms.net preparation](dankmushrooms-canonical-domain.md) before acceptance. Adapt the existing net vhost after inspecting it; do not install a duplicate vhost. Retain both signed webhook paths without redirects. Keep customer identity `shop-test.danks.store`, order identity `danks.store`, the same numeric Woo IDs and all prior ERP/inbox/MP/Clover references. Set only transport origins to net. Ecwid public routing stays unchanged until the owner later switches it; danks.store becomes a deprecated redirect to net after cutover.

Keep public Woo checkout restricted. Complete a native signed event reaching the durable inbox, MP reservation and ERP Sales Order in the same installed run. Verify a linked customer and guest mapping, real capture evidence before one ERP invoice/payment pair, partial/complete MP dispatch and stable ERP/Woo acknowledgments. Prepare a shipping label through the exact generated Woo admin order URL; only MP dispatch moves stock. Pickup/local delivery require no postage. Any charge or postage purchase is an explicit owner action.

## Opening stock and ownership — cutover only

Today Ecwid stays authoritative for its active listing. At cutover, pause Ecwid checkout and all competing stock writers, keep Woo public checkout restricted, reconcile outstanding orders/holds and any pending stock API receipts, then review exact Woo product/variation/SKU mappings in `published_inventory` of the private worker config. MP's read-only owner preview shows the selected pool and current owner.

For each reviewed Woo pool, run MP's explicit owner-handoff command with its MP ecommerce ID and the expected current owner ID. Save the returned owner receipt. The handoff changes only primary listing flags and refuses pending Ecwid writes or mapping/owner drift; it does not relink Customers, orders, external IDs, stock movements or accounting. Do not infer approval from a product name or choose all Woo rows automatically.

Then use the already configured private interpreter/environment and worker config:

```bash
cd ~/RootedOps
test -n "${ORDER_PYTHON:-}"
test -n "${LIVE_ORDER_CONFIG:-}"
"$ORDER_PYTHON" integrations/commerce/production_order.py publish \
  --config "$LIVE_ORDER_CONFIG"
```

Success: reviewed Woo stock readback, stable represented order/line deductions and no duplicate pools. Stop on `Woo publication requires the reviewed inventory pool owner`, missing schema or identity/source-key mismatch. Do not bypass the owner check or substitute zero quantities. The timer remains disabled until this pass and the restricted owner purchase lifecycle pass. Routine replenishment and fulfillment then publish MP availability automatically through the reviewed timer; manual opening reconciliation is not the ongoing procedure.

Continue the restricted owner purchase after the final hostname/HTTPS change. Trace Woo ID → inbox receipt → MP order/reservations/committed movement → ERP Sales Order/invoice/payment/shipment receipt → Clover capture. Prove replay, cancellation of unshipped units and retry of a failed destination without repeating physical movement or accounting. Keep unresolved mapping/payment/refund cases in review. Settlement/fee evidence and first-payout reconciliation remain on the Ecwid retirement checklist; Clover Flex is independent.

## Rollback

Restrict Woo checkout, preserve accepted Woo orders/payments and pause its stock publisher before owner reversal. Use MP's recorded owner-receipt restore function; it verifies unchanged pool membership/specifications/flags and preserves stock and operational receipts. Reconcile current Ecwid availability/readback including Woo commitments before reopening Ecwid checkout. Never restore the pre-sale DB or reset the accepted Coco baseline/delta. Both hostname routes and inbox delivery must continue handling signed requests during recovery.

If 059 itself is faulty, restore active owner handoffs before its function-only rollback, with Woo processing paused. Do not roll back the independent Ecwid migration 058 as part of this step. Use the canonical-domain runbook for transport/content rollback; retain newer orders, links and receipts.
