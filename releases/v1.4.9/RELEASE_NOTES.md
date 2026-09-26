# RootedOps v1.4.9 — Issue #7 Phase 3

## Profile-aware Plaid API client routing

Phase 3 centralizes Plaid API credential selection in a server-side client that
resolves credentials from the Plaid Connection Profile assigned to the local
Plaid Item.

The controlled historical Plaid backfill now uses that Item-bound client for
live Item checks, Hosted Link operations, account retrieval, transaction
retrieval, and temporary Item cleanup.

The existing `legacy-current` profile continues to bridge the current ERPNext
`Plaid Settings` credential context through references; no access tokens,
Items, cursors, Bank Accounts, or Bank Transactions are rewritten by this
phase.

Raw credentials remain server-side and are not included in client
representations, operator status, or profile-aware error messages.
