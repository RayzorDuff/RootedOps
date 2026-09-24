# RootedOps v1.3.1

Release date: 2026-09-24

## Summary

Issue #8 Phase 4 adds direct Payroll Entry visibility and accounting-consistency verification for employee-specific payroll settlement.

## Added

- Live Payroll Entry employee-payment status table and settlement totals.
- Per-JE verification against Salary Slip net pay, employee Payroll Payable, checking account, and structured RootedOps linkage.
- Regression tests for correct and mismatched employee-payment accounting and batch totals.

## Changed

- Employee-payment draft creation verifies actual JE rows before commit.
- Status review exposes accounting mismatches and conflicts.

## Component version

- `rootedops_payroll`: `0.2.1`

## Release policy

This is an incremental development phase. It intentionally receives no Git tag. The next minor/tagged release should represent verified closure of one or more issues.

## Out of scope

- Payment transmission.
- ACH/NACHA generation.
- Historical accounting rewrites.
