# RootedOps 1.5.2

## Issue #7 Phase 6

- Made historical Plaid backfill explicitly profile-aware at the credential-context boundary.
- Recorded the actual Plaid Connection Profile separately from the historical backfill recipe/profile.
- Pinned the connection profile for a staging session and refuse profile drift before inspection, preparation, import, or cleanup.
- Included the connection profile in dry-run reports, import plans, private import receipts, and safe operator responses.
- Added tests for assigned-profile resolution, profile drift rejection, and missing-profile rejection.

No production Plaid Item, access token, cursor, Bank Account, or Bank Transaction is changed by this phase.
