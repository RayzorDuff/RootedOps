# RootedOps v1.4.7

Release date: 2026-09-26

## Issue #7 — Plaid Connection Profiles — Phase 2

This phase establishes the explicit relationship between ERPNext's existing
Plaid Item representation and a RootedOps Plaid Connection Profile.

### Added

- `Bank.plaid_profile` as a Link to `RootedOps Plaid Connection Profile`.
- Centralized helpers for resolving a Plaid Item's explicit profile without
  silently falling back to the default profile.
- Safe pre/post migration snapshots using state fingerprints rather than raw
  credential or synchronization-state values.
- An explicit, idempotent legacy migration function for assigning existing
  Plaid Items to a selected profile.
- Regression tests for migration verification and preservation invariants.

### Deliberate non-changes

- Existing ERPNext `Plaid Settings` remain authoritative for live Plaid API
  operations.
- Existing Plaid access tokens are not changed.
- Existing transaction synchronization is not changed.
- Link/Hosted Link behavior is not changed.
- Historical import and webhook behavior are not changed.
- No second live Plaid credential set is introduced.
- Legacy Item migration is not run automatically by `bench migrate`.

### Migration safety

The migration must be run explicitly after the intended connection profile has
been created and verified. It does not call Plaid or recreate Items. It verifies
that Item state, Bank Account counts, and Bank Transaction counts are unchanged
before committing the profile assignments.
