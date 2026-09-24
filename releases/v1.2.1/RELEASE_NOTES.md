# RootedOps v1.2.1

Release date: 2026-09-24

## Summary

Deployment hotfix for RootedOps v1.2.0. It makes the custom payroll app public assets available to the ERPNext frontend through the same shared apps volume used by the backend and maintains the Frappe assets symlink during configuration.

## Fixed

- Mount `erpnext_apps` read-only in `erpnext-frontend`.
- Ensure `sites/assets/rootedops_payroll` points to the deployed app `public` directory.
- Document the repository-to-shared-volume deployment path for custom payroll app updates.
- Remove the need to run `bench build` for the current `Payroll Entry` `doctype_js` hook.

## Component version

- `rootedops_payroll`: `0.1.1`

## Functional scope

No payroll accounting behavior changes are introduced by this hotfix. Issue #8 Phase 2 remains the functional baseline from v1.2.0.
