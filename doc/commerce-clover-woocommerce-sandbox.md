# Clover Payments for WooCommerce — sandbox credential and checkout handoff

Status: preflight/review only. Dank Mushrooms WooCommerce drafts and MP stock
recurring sync are in place. Ecwid remains production checkout; do not
activate Woo public checkout, retire Clover POS, change subscriptions, or
send real card charges.

## Credential distinctions

The existing RootedOps `CLOVER_ACCESS_TOKEN` with
`CLOVER_API_BASE_URL=https://api.clover.com` belongs to the legacy
platform/POS operations. It is **not proof** of Clover Ecommerce API
permission or sandbox payment readiness. Do not overwrite it.

The **official Clover Payments for WooCommerce** plugin requires a
**sandbox Merchant ID**, **Public Key**, and **Private Key** for an
Ecommerce token with integration type `Hosted iFrame + API/SDK`.
Use sandbox keys only against the sandbox environment. The official
plugin itself is free; merchant payment fees/entitlements must be
confirmed for live ecommerce with Clover. Do not authorize a merchant
plan change or extra cost to obtain sandbox access.

Clover documentation:
- https://docs.clover.com/dev/docs/woocommerce
- https://docs.clover.com/dev/docs/configuring-the-clover-payment-extension
- https://docs.clover.com/dev/docs/setting-up-an-api-token
- https://wordpress.org/plugins/clover-payments-for-woocommerce/

A Clover dashboard sign-in, two-factor authentication and browser location
permission may be required before token creation. Credentials for this
specific merchant live in Clover's dashboard and should be entered
**directly into the plugin's WooCommerce settings** using its credential
storage mechanism; do not paste keys into GitHub issues, chat, shell
history or `.env.example`. Do not invent fake merchant IDs or keys.

## Staging host read-only preflight

On Dank Mushrooms host, after reviewing/merging the PR:

```sh
cd ~/RootedOps
git pull --ff-only origin main
sudo docker exec -i dank-store-test-dank-wordpress-1 php -l < scripts/commerce_clover_plugin_preflight.php
sudo docker exec -i dank-store-test-dank-wordpress-1 php /dev/stdin < scripts/commerce_clover_plugin_preflight.php
```

This refuses any WordPress `home_url` other than
`shop-test.danks.store`, reports the installed Clover plugins, activation
state, Woo version, configured gateway identifiers and only
`configured`/`missing` credential presence. It **never prints secret
values or changes plugin settings**. If no Clover plugin is installed,
install the official free plugin `clover-payments-for-woocommerce` through
WordPress > Plugins > Add New. Compare installed version and compatibility
with the active WP 7.1.4 / PHP 8.3 / Woo runtime before proceeding; do not
install the unrelated paid `Clover for WooCommerce` extension or Clover POS
sync tool.

## Obtain or reuse sandbox Ecommerce keys

1. Log into the official [Clover developer dashboard](https://www.clover.com/developers)
   and switch to the **Sandbox** environment. Select or create a
   sandbox test merchant (separate from the live Dank Mushrooms merchant).
2. Launch the test merchant dashboard, then Settings > View all settings >
   Ecommerce > Ecommerce API Tokens. Complete 2FA/location requirements
   if presented.
3. Reuse an existing **Hosted iFrame + API/SDK** sandbox token for that
   sandbox merchant if available. Otherwise create this token type;
   Clover may allow only one Ecommerce token per merchant, so do **not**
   delete a token in use by any other integration.
4. Record the sandbox Merchant ID, Public Key and Private Key in the
   Clover/WordPress secrets interface. Never put any real token in repo
   or logs.
5. In the Dank WooCommerce dashboard open WooCommerce > Settings >
   Payments > Clover Payments > Manage. Select **Sandbox** and enter
   the sandbox Merchant ID, Public Key and Private Key. Select the
   intended sandbox payment action (first `Authorize only` where
   supported). Save with gateway disabled for public checkout until
   isolated test acceptance.
6. Run the read-only preflight again. Review `environment=Sandbox`,
   credentials presence and correct merchant account; do not infer a
   successful remote payment from key presence alone.

**Do not enable live checkout** merely because plugin credentials saved.
The Woo drafts should remain hidden, and no customer-facing payment method
should be exposed outside a controlled test. Any change to payment
settings must be backed up and reversible.

## Acceptance with test orders

Use **Clover-provided sandbox test cards only**, never a real card.
Test an isolated unpublished Woo test-product/order path after verifying
shop access restrictions and disabling transactional notifications.
Complete a sandbox authorize-only flow, inspect the Clover test merchant
transaction and Woo order/transaction IDs, and assert no live merchant
charge. Verify a sandbox capture and void/refund where applicable without
reusing a charge across tests. Compare processor amount/currency/tax
with the Woo order and ensure an idempotent ERP financial reference and
MushroomProcess reservation path before calling paid order lifecycle
accepted. Check failure/cancellation/duplicate webhook and replay too.

Clover sandbox credentials must be independent from live POS credentials;
proof of successful transaction and Woo order state is required before
opening live checkout. Fees, settlement, production ecommerce entitlement
and no-subscription-upgrade compatibility remain merchant-confirmation
items. Preserve Ecwid live stock sync and staging Woo draft-only inventory
writer throughout.
