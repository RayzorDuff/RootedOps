# RootedOps 1.5.29

MP dispatch can publish stable shipment quantities independently to Woo and ERP. A disabled-by-default Woo integration accepts published-stock snapshots that account for native Woo deductions and MP holds/shipments. Cancellation release waits for MP reconciliation. Tracking replacements preserve physical movement identity.

The [fulfillment runbook](../../doc/commerce-fulfillment-launch.md) covers the existing Linode, shop-test rehearsal with production ERP, ordered MP migrations, private configuration, label preparation, automatic stock publication and rollback. The companion MP change keeps scanning/packing separate from dispatch for Products and sellable whole Lots.

Local commerce tests and disposable CI provide development evidence. Production deployment, installed label capability, live owner charge/postage and hosted acceptance remain operator steps. Per-order tax and financial review remain explicit. Clover Flex is a separate project. This phase patch creates no Git tag.
