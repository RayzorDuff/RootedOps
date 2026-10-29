# RootedOps v1.4.0

Release date: 2026-09-24

## Summary

RootedOps v1.4.0 completes Issue #8, replacing consolidated employee net-pay settlement accounting with one employee-specific full-net-pay Journal Entry per submitted positive-net-pay Salary Slip while preserving consolidated payroll accrual, withholding-reserve transfer, and tax-remittance behavior.

## Employee-specific payroll settlement

The completed workflow now provides:

- employee-level payroll payment-method configuration;
- one draft Bank Entry JE per eligible Salary Slip/employee;
- Salary Slip net pay as the authoritative settlement amount;
- structured Employee, Salary Slip, Payroll Entry, payment-method, logical-payment, and payment-attempt metadata;
- preflight validation before any employee-payment JEs are inserted;
- duplicate prevention for active draft/submitted payment attempts;
- cancelled-attempt history plus safe replacement attempts;
- conflict detection for multiple active payment attempts;
- live Payroll Entry payment status and settlement totals;
- accounting consistency checks against the actual JE account rows;
- independent employee-payment records suitable for bank reconciliation.

Historical consolidated employee-payment JEs are not automatically rewritten. Active legacy employee-payment JEs continue to block prospective employee-specific settlement to prevent duplicate clearing of Payroll Payable.

## Acceptance/regression coverage

The Issue #8 regression suite covers:

- multi-employee payroll with separate JEs;
- mixed payment methods;
- existing single-employee behavior;
- zero-net-pay Salary Slips;
- logical identity and attempt keys;
- draft/submitted duplicate prevention;
- cancelled-attempt regeneration;
- multiple-active-attempt conflicts;
- cent-accurate accounting against Salary Slip net pay;
- Employee-party Payroll Payable attribution;
- checking-account credit reconciliation;
- batch settlement/outstanding totals.

## Documentation

See `doc/ISSUE_8_EMPLOYEE_PAYMENT_SETTLEMENT.md` for the final accounting boundary, workflow, lifecycle, historical behavior, reconciliation model, and handoff to Issue #6.

## ACH/NACHA handoff

Issue #6 will consume the completed employee-specific settlement model. ERPNext Company `tax_id` is the source of truth for the Dank Mushrooms EIN; RootedOps should derive High Plains Bank's NACHA Company ID as `1` plus the normalized nine-digit EIN rather than storing a second EIN value.

## Versioning

- RootedOps: `1.4.0`
- `rootedops_payroll`: `0.3.0`

This is an issue-completion minor release and should receive the annotated Git tag `v1.4.0` after the release commit is pushed.
