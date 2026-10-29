# RootedOps v1.4.6

Release date: 2026-09-26

## Issue #7 — Plaid Connection Profiles — Phase 1

This phase establishes the generic Plaid credential-context boundary without
changing existing Plaid Items, access tokens, transaction cursors, Bank
Accounts, Bank Transactions, or production synchronization.

### Added

- `RootedOps Plaid Connection Profile` DocType.
- Generic profile identity, display name, enabled/default state, Plaid environment,
  and protected credential-reference fields.
- Server-side profile credential resolution from Frappe/site configuration or
  environment variables.
- Safe profile-status inspection that never returns raw credentials.
- Validation preventing duplicate default profiles and invalid profile names or
  environments.
- Regression tests for generic profile names, environment resolution, and
  credential redaction from status responses.

### Security boundary

Raw Plaid client IDs and secrets are not stored in the new DocType. The profile
contains only references to protected configuration keys. Credential values are
resolved server-side for later Plaid API calls.

### Deliberate non-changes

- Existing ERPNext `Plaid Settings` remain authoritative for the current
  production integration.
- Existing Plaid Items are not migrated in this phase.
- Existing Bank Accounts and Bank Transactions are untouched.
- No Link session, token exchange, transaction synchronization, historical
  import, webhook, or Item-removal behavior is changed yet.
- No second Plaid credential set is introduced by this patch.

### Next Issue #7 phase

The next phase can introduce the Item/profile relationship and controlled
legacy migration, after the profile foundation has been deployed and verified.
