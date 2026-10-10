# RootedOps 1.5.20

RootedOps Issue #1 Phase 1 follow-up allows a corrected SignatureGate payload
to retry only after the prior integration event failed.

This supports audited source-data corrections, such as correcting a confirmed
cash-deposit date after a failed bank-match attempt, without deleting the
RootedOps idempotency record.

Succeeded and in-progress events continue to reject changed payloads.

No Git tag is created because Issue #1 remains open.
