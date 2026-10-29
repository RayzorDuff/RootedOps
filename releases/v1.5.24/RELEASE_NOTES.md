# RootedOps 1.5.24

RootedOps Issue #1 fixes ERPNext Bank Entry validation for confirmed
SignatureGate cash deposits.

Cash-deposit Journal Entries now include the required ERPNext Bank Entry
reference number and reference date. The SignatureGate deposit slip/reference
is used when present; otherwise RootedOps uses a stable batch-based fallback.
The confirmed actual deposit date supplies the reference date.

The failed production attempt did not create a Journal Entry or reconcile Bank
Transactions, so the same source event can be retried safely.

No Git tag is created because Issue #1 remains open.
