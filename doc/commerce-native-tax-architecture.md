# Dank Mushrooms — native ERPNext sales-tax architecture

**Status:** Installed configuration inventory prepared; **no live tax-rate
activation authorized**. This is a separate workstream from the completed
132-product Ecwid catalog import.

## Authorities and distinctions

Source: Colorado Department of Revenue's DR 1002 / GIS, Sales Tax Guide and
Tax Rule guidance, the Town of Johnstown sales/use tax notice, and ERPNext v16
tax documentation. Validate rates for the **specific transaction destination
address and tax effective date**, including city, county and special districts.

- Johnstown's published municipal sales tax is **3.5%**, collected by the state;
  this is one component, **not** a complete jurisdiction rate.
- Colorado's published state sales-tax rate is **2.9%**; other destination
  components can apply. Do **not** add fixed county/district rates without
  confirming the actual destination. Johnstown spans county boundaries.
- In general, a customer receiving items at Dank Mushrooms' location is a
  different sourcing case from items shipped to the buyer. Origin-only
  assumptions are not appropriate for web checkout.
- Fresh culinary mushrooms sold for home consumption may qualify for
  Colorado's food exemption. Johnstown states it has no municipal sales-tax
  exemptions. Food classification, whether a specific packaged mushroom
  qualifies, and applicable county/district exemptions require verification;
  do not assign the same exemption to grow kits, grain/substrate, lab supplies,
  cultures or other products by association.
- Separately stated shipping and destination-specific taxation require their
  own review. A marketplace, a direct web store and market/event transactions
  can have different collection/reporting responsibilities.

Official references:
- https://johnstownco.gov/426/Sales-and-Use-Tax
- https://tax.colorado.gov/how-to-look-up-sales-use-tax-rates
- https://tax.colorado.gov/DR1002
- https://tax.colorado.gov/sales-tax-guide
- https://tax.colorado.gov/SUTS-FAQ
- https://docs.frappe.io/erpnext/setting-up-taxes
- https://docs.frappe.io/erpnext/tax-category
- https://docs.frappe.io/erpnext/tax-rule
- https://docs.frappe.io/erpnext/item-tax-template

## ERPNext native design

| Native object | Purpose |
| --- | --- |
| Account (Tax type / appropriate liability account) | Liability for each tracked jurisdiction component |
| Tax Category | Standard taxable, food-home-consumption, exempt/non-taxable, etc., as confirmed |
| Sales Taxes and Charges Template | Transaction tax components and posting accounts for a **specific** jurisdiction/tax treatment |
| Tax Rule | Select template by customer/address/destination and effective dates |
| Item Tax Template | Per-item or category treatment that overrides selected tax-account rates where confirmed |
| Address / customer tax context | Carries the authoritative ship-to/pickup sourcing context |

Treat a zero-rate taxable sale, an item not subject to a particular tax
component, and a transaction-specific exemption as **different states**.
Do not invent tax exemptions or copy Ecwid's old configuration. Resolve
jurisdiction from the validated destination before selecting a template.

**Fail closed for unknown jurisdiction or unknown item taxability.** If the
destination cannot be confidently resolved, request operator review rather
than charge a default Johnstown rate to all addresses.

## Current installation inventory (read only)

The following script makes native Frappe read-only queries against the real
`erp.danks.store` site and identifies the company, relevant tax accounts,
existing Tax Categories, Item Tax Templates, Sales Taxes and Charges Templates,
Tax Rules and applicable field schemas.

```sh
cd ~/RootedOps
sudo python3 scripts/commerce_tax_inventory.py --repo-root "$HOME/RootedOps"
```

This does **not** create or modify companies, accounts, Items, orders,
invoices, Journal Entries, tax templates, rules, WooCommerce settings or
payroll. A successful result has `writes: false`; financial-document counts
are included to confirm scope. Do not paste unrelated ERP secrets or .env
content into an issue.

After inspecting the actual accounts and enabled tax rules, implement **only**
the missing ERPNext native configuration through a separate, idempotent,
dry-run-first operation. Link the new transaction template to the confirmed
liability accounts and include a single representative **unsubmitted**
calculation acceptance, showing taxable supplies and food treatment separately.
Do not activate any default or broad checkout rule until that acceptance
passes.

## Installed inventory findings and narrow foundation change

The owner ran `scripts/commerce_tax_inventory.py` against
`erp.danks.store` and confirmed the live company is **Dank Mushrooms, LLC
(DML)**, with **132** imported Items and **zero** Sales Orders, Sales
Invoices, Payment Entries, Stock Entries or Bins. Its Chart of Accounts
already includes `Sales Tax Payable - DML` (a leaf current liability),
`Duties and Taxes - DML` (a group Tax liability), `Payroll Tax Payable -
DML` (must not be changed), and three legacy Tax accounts labeled 4%,
6.25%, and 6%. There are three matching legacy Sales Taxes and Charges
Templates and Item Tax Templates, but no Tax Categories and no Tax Rules.

**Unsafe default discovered:** `US ST 6% - DML` is the live company's
default Sales Taxes and Charges Template, despite having no verified
jurisdiction logic. The default setting `determine_address_tax_category_from`
is currently `Billing Address`, while
`add_taxes_from_item_tax_template=1` and
`add_taxes_from_taxes_and_charges_template=0`. These existing settings
must be considered when the installed order-flow mapping is connected.

The script `scripts/commerce_tax_foundation.py` proposes the smallest
reversible native configuration:

- Create **Colorado State Sales Tax Payable - DML** and **Johnstown
  Municipal Sales Tax Payable - DML** as separate leaf Tax liability
  accounts under `Duties and Taxes - DML`.
- Create two **disabled**, **nondefault** Sales Taxes and Charges Templates
  for the official **2.9% Colorado state** and **3.5% Johnstown town**
  components. These are explicitly labeled **Incomplete** and are **not**
  the full destination rate.
- Clear the legacy **6% sales template default**, preserving the original
  4%, 6%, and 6.25% accounts and tax templates in place. It changes no
  historical accounts or posted entries.
- Create **no active tax rules**, change no Accounts Settings, and assign
  no Item Tax Templates to the 132 products.
- Never touch payroll, submitted sales, bank reconciliations or stock.

The default read-only mode inspects this exact native state:

```sh
sudo python3 scripts/commerce_tax_foundation.py \
  --repo-root "$HOME/RootedOps"
```

After reviewing the read-only result, the operator may execute the guarded
configuration with `--apply`. All component inserts and removal of the
legacy default are performed in **one Frappe database transaction** with
idempotent read-back assertions and protected document count guards.

This **foundation** is not tax activation. Prior to enabling any template
or Tax Rule for actual transactions, resolve the exact destination via the
Colorado Department of Revenue's GIS, verify the county and special district
components and each component's food exemption policy, then use the real
destination shipping address to select correct native ERPNext rules.
The installed WooCommerce storefront remains unpublished.

## Sales-channel and remittance model (owner-provided operations, November 2026)

Dank Mushrooms sells **fresh and freeze-dried culinary mushrooms** and
**cultivation supplies**. Its operational sales channels include Windsor and
Johnstown farmers markets, deliveries to Johnstown and surrounding communities,
and shipments to customers across the United States. Preserve source channel,
exact event/location/address, order and tax identities when receiving Clover
or WooCommerce orders.

**Important distinction: the tax owed and who has already remitted it are
separate facts.** Never treat an unverified organizer payment as an automatic
exemption, and never remit a verified organizer-paid tax twice.

| Channel | Sourcing basis | Collection and remittance |
| --- | --- | --- |
| Windsor market | Exact market venue and event date | Capture gross sales by item tax class, each envelope/tax component, recipient, amount, receipt and filing reference; distinguish tax already remitted by organizer from other taxes due separately |
| Johnstown market | Actual market venue and event date | User reports no tax collected at event; keep tax treatment **pending determination**, not globally exempt, until event rules/licensing and municipal/state obligation are verified |
| Colorado pickup | Buyer takes possession at pickup venue | Use physical pickup location; state, city, county, and special-district components can differ |
| Colorado delivery | Exact ship-to address/date | Destination sourcing; component-specific grocery-food exemptions, correct destination rate and applicable retail delivery fee |
| Other U.S. shipment | Exact ship-to state/address/date | Evaluate registration/physical or economic nexus for that state and product-specific rules; do not charge Colorado-origin tax on interstate shipments by default, or assume all out-of-state orders are exempt |

### Windsor organizer remittance: source discrepancy

The Town-operated **2026 Windsor Farmers Market** rules (Boardwalk Park)
specify an envelope payment of **3.95% town sales tax**, a **separate 5%
gross-sales fee**, and make the vendor responsible for **state sales tax**.
Windsor's current published citywide rate is **3.65%**. The exact market,
effective date and invoice/envelope receipt must be confirmed before treating
either percentage as the authoritative applied rate. The 5% market fee is
*not* sales tax. Windsor is a self-collecting home-rule municipality; a town
payment is not automatically a Colorado DOR/state-tax remittance.

Official references:
- https://www.recreationliveshere.com/DocumentCenter/View/468
- https://www.windsorco.gov/104/Business-Licensing
- https://tax.colorado.gov/special-event-sales-tax

**ERPNext accounting design:** Book taxable sale and tax liability by
jurisdiction/component. Record each documented organizer remittance as a
payment against that exact liability, with external reference and cash
payment account; distinguish whether organizer is licensed to remit on the
seller's behalf. Do **not** create a second tax obligation for the same
jurisdiction/event when the corresponding tax is independently documented
as remitted. A separate vendor/booth/gross-sales charge goes to a market
expense account. Record all gross sales (including food) separately so an
exempt item remains visible in taxable-base reconciliation.

For events for which the Colorado Department of Revenue's *special-event*
rules apply, the licensed organizer may remit **state-administered** tax
on sellers' behalf; verify the organizer's authorization and retain a
receipt. Recurring markets may have different ordinary retail licensing
requirements. A town-only envelope does not prove that state-administered
taxes were paid.

### Item taxation and fulfillment

- **Food for home consumption:** Fresh and ordinary freeze-dried culinary
  mushrooms are candidate exempt groceries for Colorado state purposes;
  confirm labeling and that a particular product is food rather than
  supplement. Municipal grocery-food exemptions may differ. Johnstown
  reports no town exemptions, and Windsor taxes grocery foods locally.
- **Cultivation supplies:** Treat as merchandise pending review; do not
  automatically extend grocery-food exemptions. Some plants/seeds and
  qualifying agricultural production purchases may have separate rules.
- **Mixed baskets:** Compute taxable base *per line and jurisdiction*, then
  aggregate tax once for the order; do not apply a single blanket food/nonfood
  rate across the whole cart.
- **Delivery fees:** Determine Colorado retail delivery fee eligibility for
  motor-vehicle deliveries of taxable items into Colorado, separate from
  separately stated delivery/freight charges.
- **Nationwide sales:** Maintain a reviewed state-by-state nexus/registration
  status and effective dates before attempting collection. A zero-tax
  destination because no duty to collect exists is not equivalent to an
  item being legally exempt.

### Required order/tax evidence

At the ERPNext tax calculation boundary preserve: order and original channel
identities; point-of-sale event name/date, pickup location or destination
address; sale date; product classification; quantity and gross sales; each
jurisdiction component, tax rate and exempt base; tax collected from buyer;
tax accrued; tax remitted; recipient; payment and external filing reference;
and any marketplace/event-operator remittance evidence. Do not infer
payment from Clover card settlement alone.

**Do not enable the two incomplete disabled templates or populate broad
Tax Rules until the actual location and grocery/exemption policies are
resolved.** The existing 132 imported drafts remain unchanged.

## Provider-neutral tax quote contract for installed orders

The first implementation is
`rootedops_commerce.tax_contract.validate_quote` (pure, no network or
database writes), called by
`rootedops_commerce.order_service.validate_draft` when an incoming
order event contains `tax_quote`. It does **not** activate a tax provider.

The quote interface takes a jurisdiction-resolved, immutable tax result.
A future provider may be a Colorado GIS-backed adapter, a reviewed manual
local-market calculator, or a commercial tax-calculation service. **The
interface is not a tax table or a pre-approved collection nexus.**

Minimum input is:

- `schema_version: 1`, `provider`, `quote_id`, `source_order`,
  `currency: USD`, `channel` (market/pickup/delivery/shipping),
  `location_ref` and `jurisdiction_evidence` (what address/event
  jurisdiction determination was used), plus
  `collection_status` (collect / not_required / pending).
- One ordered `lines` entry per reviewed ERPNext draft line, with
  `line_index`, `item_code`, `quantity`, `line_total` and reviewed
  `tax_class` (grocery_food / cultivation_supply / other_reviewed).
- One `components` entry for each **line and jurisdiction**, including
  `line_index`, `authority`, `jurisdiction_id`, `account_head`,
  `taxability`, `taxable_base`, `rate_percent` and `tax_amount`.
- `tax_total` and `calculated_total` must reconcile the source
  order, every line and every tax component to the cent.

When the ERPNext order integration is enabled, a supplied quote is
validated against the reviewed draft. It must exactly match the
`Actual` tax rows, source order ID, USD total and tax component arithmetic.
The installed service additionally requires site-configured `commerce_tax_provider` and `commerce_tax_item_class_map` to match the quote's provider name and every SKU's reviewed product tax classification. No provider or product classification is implicitly trusted. The integrated service also looks up each tax account in ERPNext,
restricts it to a non-group DML liability, and requires the trusted
**site configuration** `commerce_tax_account_map` to map
`authority|jurisdiction_id` to the exact permitted tax account. This
prevents an external tax provider from choosing an arbitrary ledger account.

**Backward compatibility:** `commerce_tax_quote_required` defaults
to false. Orders without a quote continue to be validated through the
existing reviewed-draft contract and keep the same replay fingerprint.
Once the installed tax provider, destination sourcing, category review and
checkout have passed acceptance, set `commerce_tax_quote_required` to
true for that isolated commerce site. Until then do **not** enable that
setting, and do not enable Woo tax/checkout or activate unresolved tax
templates. Tax quotes are checks, not a calculation engine.

For example, a 2-unit grocery mushroom line and a cultivation supply
line sold at Windsor's Boardwalk Park market may have distinct Colorado
state taxable bases while both have Windsor municipal taxable bases.
The provider must supply the actual jurisdiction rules for the relevant
date; the pure contract only checks the resulting arithmetic. The
contract does **not** assume the historical Windsor rate or a permanent
tax treatment for any product.

### Market envelope payments are *not* quote credits

A Windsor market manager's documented tax-envelope receipt must be
associated with the applicable **Windsor municipal liability and
market event**, not subtracted from Colorado state tax collected or
from the gross sales tax quote. The new contract explicitly rejects
`remittances` or `payment_credit` inside a tax quote. A separately
reviewed remittance settlement workflow must record recipient, amount,
date, market event, liability account and external confirmation.

This keeps four distinct statuses auditable: exempt item,
no-collection obligation due to nexus, municipal tax already
remitted, and tax still payable to another jurisdiction.

### Remaining implementation gates

1. Produce authoritative source classification for the imported 132
   products (not name guesses), including both forms of grocery mushrooms
   and taxable cultivation supplies.
2. Implement a real authoritative jurisdiction/nexus lookup provider,
   effective-date handling and verified collection obligations. Nationwide
   tax cannot be calculated from ZIP codes or a default Johnstown rate.
3. Integrate per-channel remittance receipts with the correct municipal
   liability, separate from tax quote calculation.
4. Perform one installed mixed-product order calculation and replay
   acceptance **without** publishing products, submitting invoices or
   enabling gateways; only then turn on stricter production tax requirements.

## Approved product classifications and real-provider request boundary

A one-time human review of **all 132 imported Items** is needed before
production quotes can be accepted. The source snapshot is private and
immutably bound to SHA-256
`0b4eec40a1cfd1d62551e2ac951a42dac21984f34ffb2d03f9aea697d1d713a8`.
The catalog includes 22 originally reviewed products and 110 remaining
products (including disabled POS/other category entries). Product names,
WooCommerce category IDs, and source-enabled status are **not** sufficient
to infer legal taxability.

Prepare a **private, unclassified CSV** locally:

```sh
cd ~/RootedOps
python3 scripts/commerce_tax_classification.py \
  --source "$HOME/commerce-migration/ecwid-full-catalog-source.json" \
  --prepare "$HOME/commerce-migration/tax-review-132.csv"
```

Each row contains the existing SKU, Ecwid product ID/name/status/source
categories, plus blank `tax_class` and `review_note` columns.

For the present catalog, the owner confirmed **40 grocery food** products
(including conventionally packaged Reishi, Turkey Tail, and future
culinary Breakfast Blend), **78 cultivation supplies** and **one
other-reviewed merchandise item**. This classification is for ordinary
culinary products as sold, not a determination for future tinctures,
extractions, supplements or related wellness-claim goods.

**Thirteen generic dollar-amount POS buttons** are not actual identified
products and must remain out of the future tax-calculated checkout
workflow. These review CSV rows retain an **empty** `tax_class` and
must explicitly set `review_status=excluded_pos` with an explanatory
`review_note`. The approval tool checks that the underlying original
Ecwid product name really is a generic amount button; it does not let
an arbitrary product escape classification. A separate `blocked_item_codes`
list is emitted in the approved local mapping JSON, and **no tax class**
is created for these 13 items.

The operator must exclude those 13 SKUs from future WooCommerce/Clover
checkout publication and enforce their rejection at the order
ingress. Having an excluded SKU in the approval artifact alone
**does not** disable the Woo product or the existing checkout. Never
classify a generic `NOTAX` label as an exemption.

The owner-approved CSV artifact should be copied to the server as a
private review file before running the approval step. The reviewed
artifact intentionally remains outside the repository. The approval
still verifies all **132** original SKU-to-Ecwid-ID pairs and refuses
changes to the original source hash; only **119** become approved
`item_classes` entries.
 The owner
must explicitly select one of `grocery_food`, `cultivation_supply` or
`other_reviewed` and provide a short product-specific rationale for
**every SKU**, including disabled/legacy POS entries. `other_reviewed`
means an explicitly reviewed other classification, **not** automatic
exemption. Additional tax categories (e.g., supplements) will need
explicit contract/schema changes rather than being misclassified.

Approve the reviewed file offline:

```sh
python3 scripts/commerce_tax_classification.py \
  --source "$HOME/commerce-migration/ecwid-full-catalog-source.json" \
  --approve "$HOME/commerce-migration/tax-review-132.csv" \
  --reviewer "Dank Mushrooms owner" \
  --output "$HOME/commerce-migration/tax-class-map-132.json"
```

The resulting `0600` JSON maps each approved ERP Item SKU to the reviewed
tax class and records reviewer, review CSV checksum, source hash, and explicit\nblocked identifiers for generic price buttons.
The command **never** changes ERPNext, products, tax rules, WooCommerce or
permissions. Keep the CSV and mapping out of the Git repository. The
approved mapping is an input to the eventual ERPNext
`commerce_tax_item_class_map` configuration, not an instruction to
enable checkout or claim all grocery products exempt everywhere.

### Replaceable tax calculation provider

`integrations/commerce/tax_adapter.py` creates a deterministic,
SHA-bound request including the approved class for each line, an **actual
street address** for market/pickup/delivery/shipping sourcing, order
identity, channel and transaction date. ZIP-only destinations fail closed.
An unknown SKU, missing tax class, unsupported shipping fees or discounts,
or a missing provider also fail closed. No state-by-state rate tables are
hardcoded.

`get_quote(request, provider_name, provider)` accepts an injected,
authenticated provider transport and requires response provider/order/
line/class/request-hash identity to match. The existing
`rootedops_commerce.tax_contract.validate_quote` then checks all
jurisdiction components, totals and the ERPNext liability mapping before
an order draft can use the quote.

**The transport is intentionally not connected to a commercial provider.**
Selecting, authenticating, and verifying a provider capable of resolving
Colorado destination boundaries and nationwide nexus is a separate
integration acceptance step. This code does not itself calculate taxes,
purchase service subscriptions, collect tax, file returns, or provide
authority for the Windsor market manager's cash-envelope remittances.
A verified source jurisdiction must include the appropriate special
districts and effective date; a recognized address alone is not a rate
determination. Colorado retail delivery fees, order discounts and shipping
charges also need explicitly defined line/fee policy before live use.

## Boundaries

- Imported 132 Items and 132 draft Woo products are already accepted. No
  reimport or new catalog test cycles.
- WooCommerce remains Coming Soon, taxes disabled, no enabled payment
  gateways or webhooks, zero published products; native ERPNext is tax
  authority, Woo must eventually show its agreed computed amounts at checkout.
- Tax work must not place live ERPNext in maintenance mode, pause payroll,
  submit sales invoices, or write stock movements.
- The installed WooCommerce → MushroomProcess → ERPNext order flow and Clover
  sandbox integration are separate acceptance gates.
