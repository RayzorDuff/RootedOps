# Native tax architecture: proposed policy and test2 fixture

Owner review required before live collection. This supersedes copying Ecwid tax
settings. The 22-product catalog checkpoint remains sufficient; the other 16
enabled records and four missing source images do not block this work.

## Authority and configuration boundary

ERPNext owns reviewed tax policy and invoice accounting. Colorado GIS resolves
the exact delivery address (or actual pickup location) into jurisdictions; it is
not replaced by a city-name or ZIP lookup. A small future quote adapter should
pass the resolved profile, item classifications, fulfillment method, shipping
terms and transaction date to ERPNext. WooCommerce consumes the resulting
component amounts and quote identity. Do not maintain a second independent rate
table or a second exemption engine in WooCommerce.

Use native configuration:

| Native object | Responsibility |
| --- | --- |
| Tax Category | Reviewed jurisdiction profile, with effective date and provenance in its configuration review; not a universal product class |
| Tax Rule | Select the company's Sales Taxes and Charges Template for that category; avoid broad city/ZIP rules and ambiguous priorities |
| Sales Taxes and Charges Template | Separate state, municipal, county and district component rows and liability accounts; no statewide combined-rate default |
| Item Tax Template | Product-class overrides for each applicable jurisdiction account, including explicit zero only where exemption is established |
| Item tax child rows | Associate a reviewed Item classification/template with the relevant Tax Category and effective date |
| Sales Invoice | Native item-level calculations, rounding and tax liability posting on submission; draft estimates do not post GL entries |

The deployed order adapter currently accepts reviewed **Actual** tax charge rows
and reconciles grand total. This can carry an approved native quote, but it does
not establish automatic destination calculation. Preserve the component accounts
and quote provenance when implementing that bridge. Before production, also
reconcile line-level rounding, discounts, refunds, shipping, and Woo tax lines.
Unknown address/classification/nexus or stale rate evidence must block checkout
for review rather than silently return zero tax. No custom rate engine is proposed.

## Product classification matrix

| Product | Proposed class | State treatment / review needed |
| --- | --- | --- |
| Fresh/raw culinary mushrooms sold for home preparation | GROCERY_HOME | Qualifying food for home consumption; state food exemption, local treatment independently resolved |
| Freeze-dried culinary mushrooms sold as ordinary food | GROCERY_HOME | Same candidate class after reviewing ordinary-food label/use; not every dried mushroom product qualifies |
| Supplement Facts products, extracts, tinctures, therapeutic/supplement products | REVIEW_NON_GROCERY | No automatic food exemption; review label, intended sale and applicable guidance before assignment |
| Growing supplies, substrate, grain bags, liquid cultures | MERCH_REVIEW | Evaluate individually; do not infer grocery or commercial-agriculture exemption from a mushroom association |
| Cultivation kits | MERCH_REVIEW | Review bundled components and applicable agricultural rules; not a home-consumption food classification by default |
| Other merchandise | MERCH_REVIEW | Review product and certificates; ordinary taxable merchandise where confirmed |

Maintain a single reviewed class per Item with evidence, reviewer and effective
date in the migration/classification manifest; do not infer tax class from a
storefront category name. Resolve that class into native Item Tax Templates for
each approved jurisdiction profile. No real catalog Items are classified by the
fixture in this PR.

## Confirmed rules and address scenarios

Colorado state sales tax is 2.9%. Johnstown's official page states 3.5% municipal
sales tax with no exemptions, collected by the state. These are **components**,
not a verified complete Johnstown destination rate. County/district membership,
rates and food treatment require the exact location and current evidence.

| Scenario | Required handling |
| --- | --- |
| Customer collects $100 qualifying culinary food at the actual Johnstown pickup address | Resolve pickup address. State component $0; town component $3.50; independently verify every other jurisdiction before offering a total |
| $100 confirmed ordinary taxable merchandise collected there | State component $2.90; town component $3.50; county/district components still unresolved |
| $100 food + $100 merchandise delivered within Colorado | Resolve recipient address, not seller origin. Apply each jurisdiction's food treatment by line, then separately evaluate shipping |
| Same cart delivered to a different home-rule city | Review that jurisdiction's own tax base/exemptions and registration rules; do not reuse Johnstown's profile |
| Interstate delivery | Review destination-state physical/economic nexus and registrations. Colorado's remote-seller $100,000 exception is not a universal interstate threshold and does not exempt a Colorado physical business |
| Delivery charge | Colorado exclusion depends on separability, separate statement and ability to choose pickup/alternative transport; evaluate actual terms and local rules rather than setting all freight to zero |

Colorado's retail delivery fee is a separate assessment, potentially relevant to
motor-vehicle deliveries containing state-taxable goods. Determine business
eligibility, including the qualified small-business exemption, before configuring
it; it is not automatically another sales-tax percentage. Johnstown PIFs are
location-specific private fees, not municipal sales tax; assess only if the
actual premises/contract establishes one.

## GIS / SUTS dependency

CDOR's production GIS provides address-specific state, county, municipal and
special-district information. Its API requires the business's SUTS registration
and GIS API key; the authenticated key page supplies the method documentation.
Neither that key nor its private API documentation is present in test2. Do not
invent an endpoint/schema or scrape address tables into a static statewide rate.

Next acceptance input: approved pickup address and a few synthetic representative
delivery addresses, current GIS responses and effective dates, local food-tax
treatment, shipping terms, product label review, and the owner's nexus/registration
review. Store private address evidence outside public Git; retain a redacted
quote/profile identity for reconciliation. Revalidate at checkout when address,
cart, shipping method or date changes. Keep the original quote on the order.

## Smallest installed configuration

`scripts/commerce_tax_fixture.py` uses the existing test2 guard and native ERPNext
APIs. It creates two dedicated liability accounts, one non-default Sales Taxes
and Charges Template, one exclusive Tax Category, one scoped Sales Tax Rule,
two Item Tax Templates, two non-stock synthetic Items and a synthetic Customer.
Only those Items reference the fixture category. The Tax Rule has no `disabled`
field in installed v16; its exclusive category and shopping-cart flag of zero
are the isolation boundary. No real Customer gets the category.

Native unsaved Sales Invoice calculations demonstrate the component model:

| Synthetic cart | Net | State component | Town component | Component subtotal |
| --- | ---: | ---: | ---: | ---: |
| GROCERY | $100 | $0 | $3.50 | $3.50 |
| MERCH | $100 | $2.90 | $3.50 | $6.40 |
| GROCERY + MERCH | $200 | $2.90 | $7.00 | $9.90 |

These are not destination quotes. No Sales Invoice is saved/submitted, no GL or
payment is created, and WooCommerce tax collection stays off. Replay checks
existing fixture values and fails on configuration drift rather than overwriting.

```sh
~/bin/test2-console-lock commerce -- sudo -n python3 \
  /home/rootedops/RootedOps-tax-run/scripts/commerce_tax_fixture.py \
  /home/rootedops/RootedOps/.test-deployment
```

Receipt: `.test-deployment/private/tax-readiness/native-components.json` on test2.
Rollback: remove the fixture Tax Rule first, disable the fixture templates/category
and synthetic Items, retain their unused accounts for audit. Do not delete posted
accounting or alter real catalog classification. Production has not been changed.

## Primary references (reviewed 2026-11-02)

- [CDOR Sales Tax Guide](https://tax.colorado.gov/sales-tax-guide): state rate, sourcing and Colorado nexus.
- [CDOR food guidance, FYI Sales 4](https://tax.colorado.gov/sites/default/files/Sales%204.pdf): food for home consumption and excluded supplements. This older publication remains linked from CDOR's current guidance index; review newer applicable rules/rulings before production classification.
- [Johnstown sales/use tax](https://johnstownco.gov/426/Sales-and-Use-Tax): town rate, no exemptions, PIF distinction.
- [CDOR local government sales tax](https://tax.colorado.gov/local-government-sales-tax): local treatment and administration.
- [CDOR Sales/Use Tax FAQ](https://tax.colorado.gov/sales-use-tax-FAQ): delivery charges.
- [CDOR GIS information](https://tax.colorado.gov/GIS-info) and [GIS API](https://tax.colorado.gov/GIS-API): address resolution and credentials.
- [CDOR retail delivery fee](https://tax.colorado.gov/retail-delivery-fee) and [retailer guidance](https://tax.colorado.gov/retail-delivery-fee-retailers).
- [ERPNext Tax Category](https://docs.frappe.io/erpnext/tax-category) and [Item Tax Template](https://docs.frappe.io/erpnext/item-tax-template); installed v16 metadata and native calculations are the implementation evidence.
