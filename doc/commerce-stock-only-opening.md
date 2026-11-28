# Stock-only public opening

Use `scripts/commerce_enable_local_stock.sh` from the pinned reviewed worktree
on the existing Linode. It backs up WordPress, preserves all current WordPress
environment values and its exact image, persists stock flags in the normal
private Compose environment, and recreates only `dank-wordpress`. Customer sync,
DB volumes, ERP services, gateway settings, existing holds, order/customer IDs,
and historical-order guards remain in place.

The local publisher uses the same reviewed `inventory_snapshot` and Woo
`rootedops_mp_stock` implementations. No new REST credential is needed. The
WordPress MP flag and exact creation cutoff enable its checkout/stock mutex.
Woo-native stock deductions absent from MP are subtracted before publication;
a represented MP hold is not subtracted twice. Every receipt includes readback.

`dank-woo-stock.timer` runs every minute. Its service performs stock publication
only: no intake, capture reconciliation, pick release, shipment acknowledgment,
or order completion. `orders.json` financial automation stays disabled. New
order webhooks queue for manual ERP review; merchant email alerts route according
to Woo settings. This is a manual-accounting launch, not unattended order ERP sync.

The activation script starts publication twice, verifies both runs, enables the
timer, and prepares an HTTP vhost for `danks.store` and `www.danks.store`, using
the existing 42-path legacy manifest. Reviewed product paths redirect to their
canonical `dankmushrooms.net` destinations; retired/unresolved paths remain 404.
Other paths preserve their path/query in a temporary redirect. It changes no DNS
and leaves the temporary manager-only checkout guard installed.

After inspecting successful stock readback, the operator points only the old
apex/www frontend records at the Linode and obtains their certificate with
Certbot's NGINX installer. Keep existing ERP, n8n, QR, mail, MX and TXT records.
Verify the old-host HTTPS redirects and current timer success before archiving
(removing from mu-plugins) `rootedops-cutover-checkout.php` for public checkout.
Keep Ecwid closed and its stock writer paused. Keep the source account/export
for history and rollback; do not transfer inventory ownership back without its
stored receipts and an inventory reconciliation.

The cart-rate issue has a native solution: Shipping Zones by Drawing's
**Enable at cart page** setting. The existing delivery-rate sorting plugin then
puts the cheapest eligible delivery first. Do not force free delivery without
checking the delivery address against the configured zone.

Physical acceptance remains outstanding: scan/pick the actual unit for order
214, dispatch in MP at handover, and verify the same committed movement in Woo
and ERP. Configuring the stock-only timer does not enable those untested paths.

If activation fails, leave checkout restricted and inspect its private receipts.
If stock publication later fails, inspect `systemctl status dank-woo-stock.service`
and its journal; last-snapshot/last-readback are in the private publisher state
directory. Restrict checkout before a rollback or any unreviewed stock correction.
