# Combined Woo launch source and operator sequence

The owner requested fewer merge/deployment cycles and one restricted purchase and
fulfillment as the primary installed acceptance. This candidate combines existing
RootedOps #111/#112/#113/#115/#116/#118/#119/#120/#124/#126, already-stacked #128,
and independent #117 with deployed main/customer/Cloudflare fixes. Settlement/fees
#114 is deferred. The original heads are retained as ancestry, not reimplemented.

## Merge order

1. MushroomProcess #123 (combined Woo packing/dispatch/shared-pool and optional cash).
2. This paired RootedOps combined source candidate, after native CI passes against
   the exact MP commit pinned in commerce-integration.yml.

Use a normal merge commit to preserve ancestor PR history. Do not separately merge
or deploy obsolete ancestor snapshots afterward. Old draft PRs remain review history
and can be reconciled/closed once the combined promotion reaches main.

## Carried-forward production state

- MP 058/060/062/063 installed and verified. Existing Product IDs/UUIDs unchanged.
- Fulfillment API and Appsmith imported; fast-list correction retained. Hosted
  063 search completed in 72.602 ms and returned zero eligible candidates for the
  selected open order; positive candidate search and real mutation acceptance are
  still pending. n8n role is `mushroomprocess_bridge`.
- RootedOps main fbe1805 / commerce 0.3.8 deployed. WordPress home/siteurl are
  https://dankmushrooms.net; authenticated reads work through Cloudflare with the
  explicit RootedOps user agent. Keep that fix and both webhook host routes.
- Seven real purchasing customer accounts linked; the administrator remains
  unchanged and unlinked. Historical Ecwid order import remains in scope as a
  separate backfill; it must not delay hostname or storefront preparation. See
  [historical orders #131](https://github.com/RayzorDuff/RootedOps/issues/131).
- Ecwid's current Coco stock matches MP net 2. Order intake, ERP cash posting and
  Woo fulfillment/publication gates remain disabled. Merge does not change them.

## Next hosted batch, after source merges

Keep Ecwid public and Woo checkout restricted. Take current MP/Woo/ERP/private
configuration backups. Apply only confirmed-missing 054, 055, 056, 057, 059 in that
order, with ON_ERROR_STOP and a stop on any failure; installed 058/060/062 are not
replayed. Optional 061 and its checked cash-packing preparation are separate from
card checkout. Grant reviewed service-role access using the checked-in operations
scripts, not PUBLIC permissions. Preserve existing holds and publication receipts.

Build the persistent ERP image including the combined commerce app, then promote
through the normal coordinated image/source/migrate procedure. A build alone is
not deployment. Preserve private credentials/flags and verify imports on backend,
scheduler and queues after restart. Do not downgrade the deployed customer code.

Configure the signed order receiver/inbox and gated reviewed-order cycle; verify
actual target databases, hostname transports, mail behavior and live Clover account.
Render the combined MP UI/workflow bundle from the current backed-up export using
prepare_cash_woo.py; preserve existing datasource/Header Auth bindings and exactly
one owner per webhook route. The prior legacy-only UI renderer is insufficient for
the new Woo section. Cash remains disabled until separately configured and tested.

Review exact Woo/MP product mappings and reservation-adjusted opening quantities.
Transfer publication ownership only in the checkout-restricted final window, after
accepted Ecwid commitments are reconciled; do not zero or clear legacy holds.
Publish/read back actual Woo stock. Do not infer all inventory from Coco's two units.

## Restricted owner acceptance and public opening

Use the consolidated operator walkthrough for one real owner order: correct
shipping/pickup/local-delivery choice and tax; authenticated signed intake returning
202; one MP hold and correct ERP Sales Order; verified Clover capture and one native
invoice/payment; label preparation via the exact Woo order when postal shipping;
scanned MP allocation/dispatch; Woo completion and stock readback. Label purchase
is not physical dispatch. Retry the same event/movement identity where appropriate
to check duplicate protection without making another sale or charge.

A successful order proves that path, not refunds, split tender, cash or payout/fees.
Configure the ongoing reviewed-order cycle and operator queue/review responsibility
before public opening; a single approved pilot ID is not unattended intake. Keep
cash/COD disabled unless its independent receipt/account approvals are accepted.
No source merge or automated fixture can authorize a charge, buy postage, switch
DNS, reopen public checkout or retire Ecwid by itself.

Continue the redirect/QR, feed ownership and rollback sections of the walkthrough.
Keep Ecwid available until the new storefront is accepted. Do not restart migration
with broad catalog/customer reimports or overwrite the installed baseline.
Historical orders are separately previewed/imported using stable source identities,
existing customer/product links and preserved source dates/statuses/totals. Keep
history imports outside live intake and suppress payment collection, stock/hold
changes, notifications, fulfillment replay and duplicate ERP accounting. Open source
orders require review against existing MP commitments before operational handover.

## Immediate performance repair before the wider rollout

The owner confirmed order-list latency disappeared when full per-order progress
was deferred to detail. Hosted diagnostics with JIT off measured inventory at 23 ms
and detail progress at 44 ms; old search still exceeded eight seconds due to
per-product eligibility calls. MP 063 now computes search progress/inventory once
and applies function-local JIT settings. After paired native CI and MP source merge,
063 has since been applied from tested commit b9e639de7ed7719eeb9097103fa605dba267d2d0.
All seven definitions matched and hosted search completed in 72.602 ms. Do not
reapply 063 or installed 060/062;
no workflow/stock-owner/checkout activation is needed for that repair. The combined
workflow JSON retains the already-working fast list query.
