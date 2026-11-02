# Reversible storefront cutover plan — not authorized for execution

Ecwid remains live until tax, sandbox checkout, paid order accounting and inventory
acceptance pass. Clover catalog synchronization is not a prerequisite.

## Prepare independently

1. Provision independent WordPress/WooCommerce hosting and database, domain/TLS,
   outgoing mail and webhook policies, monitoring, patching and restore ownership.
   Do not repurpose shared test2 or SignatureGate resources.
2. Take encrypted, versioned WordPress files/database and ERP/MP backups; prove
   restoration into isolated targets. Record backup IDs, recovery owner and time
   estimates. No rollback operation may erase post-cutover orders or payments.
3. Store production secrets in the deployment secret store, with least privilege,
   explicit environment names and rotations coordinated with their consumers.
   Do not promote sandbox keys, copy restored production credentials blindly or
   enable every restored workflow. Keep production/sandbox event namespaces separate.
4. Review tax classifications, exact pickup/destination jurisdictions, registrations,
   shipping treatment and native quote/invoice reconciliation. Accept both food
   and taxable merchandise, mixed baskets, discounts, shipping, pickup and refunds.
5. Accept the official Clover plugin with authorized merchant Ecommerce keys;
   sandbox must prove capture vs authorization, refunds, transaction identity,
   currency/tax totals and verified event replay. Confirm current merchant
   entitlement with the merchant portal/provider before any package change.

## Final source and identity checkpoint

- Export the final Ecwid catalog read-only with timestamp/checksum and source
  store/product/variation IDs, SKUs, descriptions, SEO, original images and URLs.
  Preserve the existing 22-product identity mapping and reproducible compiler;
  never reassign Woo/ERP identities during final import.
- Diff final export against that checkpoint. Review changed records individually;
  classify 12 generic POS/Disabled-category and four uncategorized enabled records
  separately. Keep 94 disabled placeholders archived, not automatically sellable.
  Preserve four absent images as accepted source gaps unless originals are available.
- Review canonical URLs, slug collisions, metadata, internal links and an explicit
  old-to-new redirect map. Verify redirects without loops and preserve analytics
  references. Export media and association mappings independently of attachment IDs.
- Reconcile final prices, sellable inventory and reservations immediately before
  publication. Catalog import does not itself authorize stock or publication.

## Controlled acceptance and cutover

1. Record go/no-go owner, maintenance window, TTL/DNS reversal, storefront routing,
   webhook enable/disable commands and acceptance evidence. Obtain cutover approval.
2. Establish one order intake authority and a precise handover timestamp. Keep
   Ecwid operational until that boundary; do not double-route the same checkout.
3. Apply final reviewed delta and backups. Enable only accepted checkout, taxes,
   inventory limits and narrowly scoped production event routes. Publish only
   approved products. Turn on customer mail only after isolated acceptance.
4. Switch storefront routing; verify redirects, certificate, checkout and receipt.
   Any live payment acceptance requires separate owner authorization. Reconcile
   Woo numeric ID/display number, processor transaction, MP reservation/physical
   shipment and ERP Sales Order/Invoice/Payment Entry. Unpaid or authorization-only
   orders must remain ineligible for paid fulfillment.
5. Monitor durable inbox retries/dead letters, duplicate events, amounts, tax
   liability accounts, stock and partial shipments. Reconcile each opening order
   through one normal lifecycle before broad traffic. Set named rollback triggers
   for tax mismatch, lost/duplicate orders, payment mismatch and overselling.

## Rollback without losing transactions

Disable new Woo checkout/event dispatch, record final Woo and processor IDs and
export the order/event delta. Route shoppers back to Ecwid and restore its intake
only after confirming there is no overlap. Preserve Woo's database, inbox and all
financial/reservation/shipment history; queued events are reconciled, not deleted.
Do not restore ERP/MP to an old snapshot over new transactions. Review refunds,
voids, unfulfilled captures and reservations individually before release.
Restore storefront configuration/files only when necessary using the tested
backup, then replay only missing effects by durable external identities. Record
the rollback timestamp, affected orders and owner reconciliation sign-off.

## Present go/no-go

Catalog migration is sufficiently proven. Production remains **no-go** until
address-based tax acceptance, a real Clover sandbox checkout with verified capture,
the installed paid accounting/reservation/partial-shipment lifecycle, and a tested
independent hosting/restore procedure are accepted. Native/mocked test suites
alone are not evidence of those installed operational gates.
