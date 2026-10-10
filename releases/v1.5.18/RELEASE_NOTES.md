# RootedOps 1.5.18

Issue #7 Phase 7 hardens compatibility between RootedOps Plaid Connection
Profiles and ERPNext's stock Plaid UI.

## Changed

- Stock Link a new bank account now assigns newly linked Banks to the RootedOps
  profile backed by the same legacy ERPNext Plaid Settings credentials.
- Stock Sync Now skips disabled Bank Accounts, tokenless Banks, unprofiled
  Items, and Items assigned to non-legacy credential profiles.
- Existing Plaid profile assignments are never overwritten.

## Safety

- The patch does not change Plaid access tokens, Bank Account integration IDs,
  Bank Transactions, cursors, or reconciliation data.
- Non-legacy Plaid profiles are deliberately excluded from ERPNext's stock
  global synchronizer until RootedOps has a fully profile-aware production
  importer.

No Git tag is created because Issue #7 remains open.
