# RootedOps Commerce 0.1.0

Separately versioned Frappe v16 app for commercial product content, ERP Item /
Item Price reads, channel identities and immutable source archives. See
`integrations/commerce/README.md` and `doc/commerce-staging.md` at repository root.

Standard Desk forms provide draft/published/retired content, descriptions, SEO,
gallery media and per-provider/site content overrides. No Webshop dependency.
Sales User can read catalog content; Sales Manager can create/edit it. Source
archives containing customer/order data are restricted to managers. Restrict
export/delete rights further through Role Permission Manager where appropriate.

The app does not make ERP stock the operational authority and does not process
payments or replay historical orders. Its own version is independent of Payroll.
