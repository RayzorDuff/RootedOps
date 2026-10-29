# RootedOps 1.5.1

## Issue #7 Phase 5

- Added profile-aware, read-only Plaid Item sync verification.
- Existing Items resolve their assigned Plaid Connection Profile before `/item/get` and `/transactions/sync`.
- Sync verification does not persist cursors or Bank Transactions.
- Added safe metadata/count response and tests for multiple profiles and cursor handling.
