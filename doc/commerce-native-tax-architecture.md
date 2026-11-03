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
