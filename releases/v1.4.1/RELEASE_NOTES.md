# RootedOps v1.4.1

Release date: 2026-09-24

## Issue #6 — ACH Phase A

This patch release begins Issue #6 without changing payroll accounting or generating NACHA files.

### Added

- ACH Direct Deposit configuration on Employee for ACH-paid payroll employees.
- Frappe `Password` storage for routing and account numbers.
- Checking/savings selection, bank name, account-holder name, authorization-active flag, and authorization effective date.
- ABA routing-number normalization/check-digit validation.
- NACHA DFI account-number length/character validation.
- Masked operational ACH configuration helper and a separately scoped internal server-side credential helper for future export.
- Permanent Issue #6 implementation notes documenting ERPNext Company `tax_id` as the authoritative EIN source and the High Plains Bank company-name/company-ID requirements.

### Security

- RootedOps ordinary ACH configuration reads never return raw routing/account values.
- Full credentials are decrypted only by the internal export helper and must not be logged, serialized to client responses, or committed to source control.

### Notes

- No NACHA file generation is included in this phase.
- No Git tag is created because this is an incremental phase of an open issue.
