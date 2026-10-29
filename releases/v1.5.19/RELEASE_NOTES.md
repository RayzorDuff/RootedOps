# RootedOps 1.5.19

RootedOps Issue #1 Phase 1 introduces the first production cross-system
accounting integration: confirmed SignatureGate cash deposit batches to ERPNext.

## Added

- Durable `RootedOps Integration Event` idempotency registry.
- Authenticated SignatureGate cash-deposit API.
- Read-only matching preflight against imported Rooted Psyche Bank Transactions.
- One Journal Entry per confirmed deposit, including multiple bank debit legs.
- Native Bank Transaction reconciliation.
- n8n orchestration with production and non-writing test modes.

## Initial production case

SignatureGate batch `31cc02f3-3477-46eb-a4e7-4f2f2a756a12` is expected to
match the existing $732 Canvas checking deposit and $5 Canvas Business Share
deposit before the Confirm action is used.

No Git tag is created because RootedOps Issue #1 remains open.
