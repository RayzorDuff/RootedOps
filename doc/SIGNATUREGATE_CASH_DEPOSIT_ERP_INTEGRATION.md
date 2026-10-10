# SignatureGate cash deposits -> ERPNext

This is the first concrete RootedOps Issue #1 integration boundary.

## Source event

SignatureGate emits one stable source key only after a deposit batch is confirmed:

```text
signaturegate:deposit_batch:<uuid>
```

SignatureGate remains authoritative for donation composition, cash custody,
deposit confirmation, and synchronization state. RootedOps remains authoritative
for ERPNext accounting and bank reconciliation.

## n8n

`n8n/SignatureGate - Cash Deposit to ERPNext.json` reuses the ERPNext
credentials already proven by the bank CSV workflow:
`ERPNEXT_PUBLIC_URL`, `ERPNEXT_API_KEY`, and `ERPNEXT_API_SECRET`.

Production mode reads the confirmed batch from SignatureGate using n8n's
existing Postgres credential, invokes RootedOps, then records success/failure in
SignatureGate. Test mode returns without touching production SignatureGate or
ERPNext so the development Appsmith branch can carry the same UI safely.

## Accounting and bank matching

RootedOps finds exactly one same-day subset of already imported, unreconciled
Rooted Psyche Bank Transactions within seven days after the SignatureGate
deposit date. The matched Bank Accounts supply debit GL accounts; the deposit
total credits `Donation Income - RP`.

The initial Canvas opening deposit is expected to resolve as:

```text
Dr BASIC BUSINESS CHECKING - Canvas Credit Union - RP  732.00
Dr BUSINESS SHARE - Canvas Credit Union - RP              5.00
Cr Donation Income - RP                                 737.00
```

RootedOps creates one submitted Journal Entry and reconciles every matched Bank
Transaction through ERPNext's native BankTransaction reconciliation path. If no
unique subset exists, accounting is not created.

## Idempotency

`RootedOps Integration Event` stores source key, request fingerprint, attempt
count, ERP document identity, and failure state. An identical retry returns the
existing Journal Entry; a changed payload under the same source key is rejected.

## Production preflight

Before confirming the first production batch:

```bash
bench --site erp.danks.store execute \
  rootedops_payroll.services.signaturegate_deposits.preview_signaturegate_cash_deposit_match \
  --kwargs '{"deposit_date":"2026-10-05","actual_amount_cents":73700}'
```

The preflight performs no accounting or reconciliation writes.
