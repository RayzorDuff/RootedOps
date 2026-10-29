# RootedOps v1.4.8 — Issue #7 Phase 2.1

## Legacy Plaid Settings compatibility bootstrap

Phase 2.1 bridges the existing ERPNext `Plaid Settings` credential context to the new RootedOps Plaid Connection Profile model.

`bootstrap_legacy_plaid_profile()` creates the initial `business` profile using explicit legacy references. The existing client ID and secret remain in `Plaid Settings`; RootedOps resolves them server-side.

The bootstrap does not recreate Plaid Items, replace access tokens, reset synchronization state, create accounting records, or call Plaid.

After the profile is created and verified, the existing Phase 2 migration can safely assign connected Items to the selected legacy profile name.
