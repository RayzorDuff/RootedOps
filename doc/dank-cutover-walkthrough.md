# Dank Mushrooms — operator walkthrough to public Woo checkout

This is the entry point for the small executable blocks. Existing Linode, current Woo installation/database and production erp.danks.store; canonical website **dankmushrooms.net**, later danks.store redirects. Keep current Ecwid public routing and rollback access until the owner switches it. No separate ERP bench, broad catalog/customer reimport or Clover Flex project is required. Current owner evidence supersedes earlier pending/no-order notes: the cash **web order completed and Products were assigned**. Preserve its records. Neither customer nor order should be recreated to test cutover.

## Block A — read-only Linode preflight; paste this output first

```bash
(
  set -eu
  cd ~/mushroomprocess
  git log -1 --format='MP %h %s'
  printf 'Modified tracked files: '
  git status --porcelain --untracked-files=no | wc -l
  python3 scripts/ecwid_inventory_publish.py inspect --ecommerce-id 1
  sudo docker exec -i mushroomprocess-bridge-postgres sh -ec \
    'exec psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' <<'SQL'
BEGIN READ ONLY;
SELECT current_database(),
 to_regprocedure('public.mp_inventory_units()') AS inventory_058,
 to_regclass('public.mp_fulfillment_allocations') AS allocation_060,
 to_regclass('public.mp_commerce_cash_receipts') AS cash_061,
 to_regprocedure('public.mp_commerce_ship_products(text,text,text,text,jsonb)') AS woo_055;
SELECT ecommerce_id,available_from_products,available_from_lots,desired_quantity
 FROM public.mp_ecommerce_catalog_inventory() WHERE ecommerce_id=1;
SELECT ecommerce_id,available_quantity FROM public.mp_commerce_inventory() WHERE ecommerce_id=1;
COMMIT;
SQL
  sudo docker exec erpnext-backend bench --site erp.danks.store list-apps
)
```

Expected: clean tracked checkout, mushroomprocess_bridge, 058 present, current finite/enabled Ecwid readback, inventory reflecting actual post-sale Products/locations/holds. 060/061/Woo functions may still be absent; passing CI does not install them. ERP app was last confirmed at 0.3.4, so a newer candidate is not presumed deployed. **Stop here** if signatures/quantities differ or a write has an unknown outcome. Do not reset Coco's accepted baseline, hardcode stock or release unidentified holds.

## Block B — review/merge source, then backup; no public switch

Review MP #120 (independent legacy Fulfillment UI/060), then #121 (cash receipts/061), then #122 (collision-safe Product IDs/062). Existing Woo MP #115 → #116 → #117 → #119 remains its own chain; merge current main into each child before final review, preserve new 060/061 and the current higher patch version rather than downgrading to an older feature snapshot. The owner supplied the #115 failure: a generated Product ID suffix collided in inventory fixture 058. #115 now has deterministic inventory fixtures; independent #122 fixes the actual Product generator and forces bulk/concurrent collision regressions. Apply 062 independently before new packaging when its reviewed source is deployed; no n8n import is needed for that function-only fix. Do not infer a deployment from those checks.

RootedOps: existing #111 → #112 → #113 → #115 → #116 → #118 → #119 → #120 → #124 → #126, then the cash-receipt PR. #117 is independent cutover documentation; #114 is settlement/fee work. Keep incomplete live order/payment PRs draft. The owner controls final merges and main → production promotion.

Use blocks B/C in [MP Fulfillment deployment](https://github.com/RayzorDuff/MushroomProcess/blob/feature/fulfillment-search-allocation/doc/fulfillment-allocation-launch.md) for verified MP backup and exact 060 apply. Use the existing RootedOps Linode backup blocks for Woo files/database, ERP and private configuration; keep an off-host recovery copy. Stop on a dirty checkout, unverified backup or partial migration. Do not replay baseline migrations.

## Block C — Fulfillment UI and cash receipt

Use block D/E in that MP walkthrough: replace the existing PGSQL Fulfillment API workflow, render/import/publish the scoped Appsmith export and prove empty search, pagination, stale-product refusal and preserved order progress with synthetic data. New Assign allocates; it no longer silently ships. Confirm MP Dispatch is the physical action. Do not repeat today's completed order.

Then follow [MP cash receipt deployment](https://github.com/RayzorDuff/MushroomProcess/blob/feature/commerce-cash-receipts/doc/commerce-cash-receipts.md) for 061, the private Header Auth credential and cash UI. Stop until unauthenticated receipt entry is refused and no Assign/Dispatch can mark payment received. The Commercial Inventory Sync schedule remains enabled; legacy Ecwid sync stays archived. Other 23 stock baselines still require review; no mass publication is authorized.

Use [cash accounting blocks 1–4](commerce-cash-accounting.md) for exact read/preview, private ERP config merge, deliberate financial post and pause. Owner inputs still required: real cash amount/time, existing ERP documents/Customer, company/cash account, exact items, tax quote and posting date. Cash entries must not use fake Clover charges. Native code/tests are supplied; no production accounting was executed by development.

## Block D — Woo schema/configuration and hostname

Follow [shared inventory handoff](commerce-inventory-owner-handoff.md) and its MP schema preflight: installed 058 is retained; apply only actually missing 054/055/056/057, then 059. 060/061 can precede them; afterward run 061's checked cash-packing preparation, which replaces only recognized packing gates. Use MP's Git renderer for the combined cash-aware Woo workflow/Appsmith bundle; do not use an obsolete raw overlay that would hide the revised Fulfillment section.

Deploy reviewed commerce app 0.3.7 through the existing production ERP candidate/image/migrate procedure, with coordinated restarts. Receiver/inbox database, MP database, active gateway environment and actual mail sink must be verified before a fixture order. Keep order/payment/stock flags disabled until that review. Keep source store identities `shop-test.danks.store` for customer links and `danks.store` for Woo orders; change only canonical transport origins to dankmushrooms.net.

[Canonical-hostname blocks](dankmushrooms-canonical-domain.md) cover private configuration, backups, serialization-safe content-only replacements, existing net/shop-test vhost edits, HTTPS and signed webhook paths. Do not install a duplicate net vhost or blanket-redirect signed POST endpoints. Verify existing-customer updates in both directions, generated Woo admin links, Google Maps browser-key restriction for https://dankmushrooms.net/*, mail and gateway/shipping connections. Owner handles DNS. Stop before URL/DNS writes until this walkthrough's preceding gates pass.

## Block E — restricted owner order and ongoing operations

Keep public Woo checkout restricted. Use the existing [Fulfillment acceptance](commerce-fulfillment-launch.md) for a native signed event returning durable HTTP 202, one MP reservation and ERP Sales Order, verified Clover capture and one invoice/payment pair, label preparation through the exact Woo order, scanned partial/complete MP dispatch, target acknowledgments, stock readback, replay and cancellation. A real charge or postage purchase is an explicit owner action; do not substitute a fixture response for native ERP evidence. Cash uses its own explicit receipt and ERP account, with native paid Woo update before dispatch confirmation.

Automatic after reviewed activation: durable intake, independent MP/ERP retry, continued snapshots for approved orders, stock publication to exact reviewed published Woo mappings, and retry of committed MP dispatch acknowledgments. Owner actions: scan/allocate, label selection/purchase, actual dispatch/handover, cash received, commercial/payment exceptions and initial tax/account/order review. Unknown mappings, refunds, settlement differences and partial/split tender remain review. Configure the ongoing multiorder cycle and queue review, not a single owner-order allowlist as the public procedure.

## Block F — switch, verify, pause/rollback

Use [the cutover/rollback Linode runbook](dank-woocommerce-linode.md) for the final sequence: verified backups/opening inventory; pause Ecwid checkout and competing stock writers; reconcile accepted commitments; transfer each reviewed pool's publication owner; publish/read back Woo opening stock; owner DNS/HTTPS/URL switch; shipped, pickup and local-delivery carts; current Woo tax totals; USPS rates and label capability; FluentSMTP; live Clover settings; restricted owner purchase. Only then open public checkout.

Repeat saved sitemap checks against net, avoiding shop-test hops. Retain 302 redirects through verification; generic dollar-amount paths are retired and Miscellaneous remains a replacement decision. Verify a separate qr.danks.store label sample. Preserve saved exports/historical references. Record Google/Ads source/offer IDs and Meta business/catalog/Pixel/shop ownership before switch, prove a small post-switch feed sample, then retire Ecwid feeds in the documented owner sequence.

To stop: restrict new Woo checkout, pause its order/payment/publication cycle, preserve signed intake and all accepted Woo orders/payments/stock receipts, reconcile outstanding orders and committed physical movement. Use recorded pool-owner restoration only after writes stop and recompute present Ecwid availability before reopening it. Preserve both signed webhook hosts during recovery. Roll back transport/content from compare-before-restore journals rather than restoring an old live DB. Cash, card refund and physical return are separate reviewed operations. Keep first-payout/fees reconciliation and Clover website-checkout entitlement after Ecwid cancellation on the **Ecwid retirement** checklist; Clover Flex is not a storefront cutover dependency.
