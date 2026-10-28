# RootedOps v1.5.27

Release date: 2026-10-27

Incremental development release: safeguards ERPNext stock Plaid synchronization against duplicate enabled Bank Account mappings to the same account in one Plaid Item, with regression tests. Retains the existing fail-closed checks for inactive accounts, unusable tokens, profile mismatch, and invalid account membership.

Adds regression assertions for the payroll tax-payment cancel/amend unique-key behavior and records operational reconciliation closeout notes with unresolved historical opening-balance exceptions. No historical accounting adjustment or migration is included.

## Deployment

Update main, run `make validate` and `make release-check`, then use `./erpnext/deploy.sh` for the custom app. Source and service verification belong to the deploy script. Run application regression tests only on a dedicated Frappe test site. RootedOps has not run those tests on the production accounting site.

## Remaining limitations

The duplicate active mapping guard operates within a single Plaid Item and does not identify two different Plaid Items which refer to the same physical account using different IDs. Do not backfill overlapping reconciled history until a cross-Item duplicate-import guard is implemented and tested. Prior bank reconciliations and historic balance exceptions remain untouched.

This is a phase-only patch release; no Git tag is required.
