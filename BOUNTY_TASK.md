# Bounty Fix

**Reward:** $30.00
**Issue:** https://github.com/RayzorDuff/RootedOps/issues/20
**Repo:** https://github.com/RayzorDuff/RootedOps

---

## Issue

Deploy Dank Mushrooms WooCommerce and migrate Ecwid catalog, customers, orders and Clover checkout

## Goal
Replace the Dank Mushrooms Ecwid storefront at https://danks.store with a self-hosted WordPress + WooCommerce storefront on the existing RootedOps Linode. Move authoritative commercial content/customer records into ERPNext and enable the existing Clover merchant service as the WooCommerce checkout gateway. **Only retire Ecwid after checkout, inventory, orders, reconciliation and archival succeed.** Free the approximately $30/month Ecwid subscription expense for Linode resources; actual net savings and Clover bundle/downgrade terms must be verified.

## Scope and boundaries
- Deploy separate WordPress container(s) and dedicated database from the Rooted Psyche WordPress instance; shared RootedOps proxy/backups/monitoring, but independent ownership, updates, credentials and content. Avoid Multisite unless reassessment finds a concrete reason.
- Use a new separately versioned Frappe v16 application, working name `rootedops_commerce`, for ERPNext commercial product descriptions, SEO/media, catalog, customers and integrations, rather than adding these to `rootedops_payroll`. Existing ERP Item includes item code/name, description, image, brand, barcodes, variants. Website Item/Webshop is absent; no Webshop installation required as a prerequisite.
- ERPNext owns Item, Item Price, commercial content, customer/accounting records; MushroomProcess owns production/package lineage, operational inventory and fulfillment; WooCommerce is a channel-specific projection. Provider-neutral n8n integration uses existing mappings, durable external IDs and idempotency.
- Clover remains live for payments; Moov/High Plains POS is a **later phase** tracked elsewhere.

## Work plan
### Audit and capacity
- [ ] Inventory Ecwid catalog, product variations/SKUs, SEO fields, media, categories, inventory statuses, customer records, order/payment history, redirects, integration credentials and subscriptions; create secure offline export/backups.
- [ ] Audit Linode CPU/RAM/swap/storage, database use, Docker services, WordPress/PHP worker needs and backup size; decide upgrade size based on measurements. Confirm estimated hosting delta vs $30/month Ecwid subscription.
- [ ] Confirm Clover/Ecwid bundled pricing and entitlement after Ecwid cancellation; verify official Clover WooCommerce plugin compatibility, current merchant credentials, gateway fees and ability to downgrade without breaking checkout.
### Implement
- [ ] Add reproducible, pinned Docker Compose WordPress/WooCommerce deployment, separate database/secrets, Nginx/TLS, staging access, volumes, health checks and backup/restore verification. Do not disrupt Rooted Psyche or existing RootedOps services.
- [ ] Build minimal rootedops_commerce Frappe app and editing experience for canonical customer-facing name, short/full description, media/gallery, SEO title/meta description, publication state and channel overrides linked to ERP Item.
- [ ] Import Ecwid commercial content into ERPNext, with provenance and field-level reconciliation for products/variants/SKUs, tax/pricing, media and SEO; resolve incomplete or duplicated mappings with MushroomProcess #80.
- [ ] Import customers/order history with stable source IDs and privacy safeguards; do not create duplicate invoices or re-trigger historical fulfillment.
- [ ] Implement n8n/RootedOps provider-neutral ERPNext + MushroomProcess → WooCommerce catalog/inventory sync, WooCommerce → ERPNext/MushroomProcess order/customer/fulfillment sync, webhook authentication, idempotency, retries and errors. Preserve Ecwid live until verified.
- [ ] Install/configure Clover WooCommerce payment plugin, then test payments, refunds, cancellations, taxes, shipping and external transaction reconciliation with ERPNext.
- [ ] Preserve QR redirect behavior at qr.danks.store and create redirects from existing Ecwid URLs to WooCommerce.
### Cutover and retirement
- [ ] Compare migrated catalog, stock, customers and order history with Ecwid exports and test both normal and exceptional checkout/fulfillment flows.
- [ ] Schedule reversible DNS/site cutover, verify HTTPS and end-to-end live checkout, backed-up records and rollback ability.
- [ ] After acceptance, disable old Ecwid publication/sync, cancel/downgrade services only after verifying Clover gateway remains functional and record final subscription savings. Retain export/history and rollback snapshots.

## Acceptance
- All required Ecwid content, media, metadata and record history are preserved with reconciled counts and durable identities.
- Canonical product editing resides in ERPNext; WooCommerce can be repopulated without Ecwid.
- WooCommerce + Clover successfully processes live transactions and maps them to ERPNext and MushroomProcess exactly once.
- danks.store and existing product QR/links resolve correctly; verified backups/restore and no regression for Rooted Psyche.
- Ecwid can be canceled safely with verified Clover merchant agreement and resource plan.

## Dependencies
RootedOps #1 (idempotency), #2 (commercial catalog), #3 (external sales documents), #4 (later Moov); MushroomProcess #12 (QR), #80 (mapping), #85 (fulfillment), #86 (catalog). Existing Rooted Psyche WordPress deployment in RootedOps #11 is a deployment reference, **not** the issue in which this storefront's work should be tracked.

## Shared restore acceptance — RootedOps #22

The infrastructure backup/restore testing requirement is consolidated in [#22](https://github.com/RayzorDuff/RootedOps/issues/22), implemented for operator rehearsal by [PR #24](https://github.com/RayzorDuff/RootedOps/pull/24). A successful recorded clean-Linode full-stack restore, service/data checks, outbound isolation, reboot and round-trip under #22 satisfies this issue's shared infrastructure restore requirement; it need not be repeated independently here. This does not mark the rehearsal passed yet or complete unrelated application acceptance. The operator will run it after merging the bootstrap/restore PR.

---

## Clover gateway migration dependency (2026-10-29)

Track the interim WooCommerce + Clover payment gateway, settlement and ERPNext/MushroomProcess reconciliation, merchant entitlement after Ecwid cancellation, and production cutover gate in **RayzorDuff/RootedOps#26**. This is required before Ecwid retirement under RootedOps #20; **RootedOps #4 (Moov)** is a later separate phase. Repository-only development can continue while the disposable test Linode is offline; merchant/plugin/live payment checks must await a new isolated staging host and explicit authorization.


## WooCommerce migration checkpoint — November 15, 2026

Woo-to-ERP customer signup provisioning, duplicate-email review, and billing-address updates have been verified on `shop-test.danks.store`. ERP-to-Woo projection is deployed at `abc03f8` and enabled. A live ERP-originated change is still awaiting verification.

Production order synchronization remains to be implemented. The existing staging order #51 used an operator-relayed Woo snapshot to exercise the durable inbox, MushroomProcess reservation path and reviewed ERP Sales Order draft. That is staging evidence for the draft flow. Native automated order delivery and invoice/payment creation are pending.

1. Deliver authenticated Woo order lifecycle webhooks through the RootedOps inbox. Key orders by store and Woo order ID, preserve event receipts, and make retries and out-of-order events safe.
2. Resolve registered buyers through the Commerce Customer Link. Use an explicit guest Customer policy with order-level addresses. Validate Item/SKU, shipping, discounts and destination tax before creating ERP Sales Orders. MushroomProcess owns reservations and fulfillment. Persist references on both sides.
3. Match verified Clover capture to the Woo order and reconcile one ERP Sales Invoice and Payment Entry. Test unpaid intake, duplicate delivery, cancellation/release, paid fulfillment, refunds and settlement before cutover. The current financial endpoint can link already submitted documents; automatic posting remains open.

See #20 for the storefront cutover, #26 for Clover and RayzorDuff/MushroomProcess#85 for fulfillment.


---

## Process

### 1. Orient yourself first
Before touching any code:
- Read the README and any relevant docs
- Run: find . -type f | grep -v node_modules | grep -v .git | grep -v dist | head -60
- Grep for the key terms from the issue title to find the relevant files
- Read the files around the bug — understand what's currently happening

### 2. Find and read the tests
- Look for test files near the relevant code (*.test.ts, *.spec.js, __tests__, etc.)
- Read them — they tell you what behavior is expected
- Understand what a passing fix looks like before writing a line

### 3. Implement the fix
- Make the MINIMAL change that fixes the issue — nothing more
- Do not refactor, rename, reorganize, or clean up unrelated code
- Do not add dependencies unless the issue explicitly requires it
- Do not modify config files (package.json, tsconfig.json, etc.) unless that IS the fix
- One logical change, one commit

### 4. Verify
- Run the test suite: check package.json scripts for "test", "lint", "typecheck"
  Common commands: npm test, yarn test, pnpm test, pytest, go test ./..., cargo test
- If TypeScript is present: npx tsc --noEmit
- Fix any test failures your change caused — if a test was wrong before, update it

### 5. Commit and document
- git add -A
- git commit -m "fix: Deploy Dank Mushrooms WooCommerce and migrate Ecwid catalog, customers, "
- Write AGENT_SUMMARY.md with:
  - Root cause: what was wrong and why
  - Fix: what you changed and the reasoning
  - Verification: how to confirm it works
  - Concerns: anything a reviewer should know

---

## Stop conditions

If ANY of these are true, write "UNCERTAIN: [reason]" at the top of AGENT_SUMMARY.md, make NO code changes, and stop:
- The fix requires changing more than ~5 files
- You cannot determine what the correct behavior should be
- The issue requires a database migration, API key, or external service
- You find 3+ open PRs already attempting this fix (high competition)
- The repo is not in a language/framework you can reason about confidently

A clean UNCERTAIN is better than a bad PR.
