# RootedOps v1.2.0

Release date: 2026-09-24

## Summary

This incremental RootedOps payroll release advances Issue #8 through Phase 2. It establishes employee payment-method configuration and changes net-pay settlement accounting from one consolidated payment draft to one draft Bank Entry Journal Entry per submitted Salary Slip/employee.

## Highlights

- Adds Employee payroll payment-method configuration used by downstream payment workflows.
- Creates one draft employee-payment Journal Entry per positive-net-pay submitted Salary Slip.
- Links each payment draft structurally to Employee, Salary Slip, Payroll Entry, payment method, and a stable payment key.
- Preflights the entire payment batch before creating Journal Entries.
- Refuses duplicate active payment JEs for the same Salary Slip.
- Preserves the existing consolidated payroll accrual, tax-reserve transfer, and tax-remittance workflows.
- Blocks employee-specific settlement when a legacy consolidated employee-payment JE is already linked to the Payroll Entry.

## Deferred to later Issue #8 phases

- Cancel/amend and regeneration lifecycle behavior.
- Rich payment-status presentation and management UI.
- Partial payroll payments.
- ACH/NACHA file generation or payment execution.

## Component version

- `rootedops_payroll`: `0.1.0`
