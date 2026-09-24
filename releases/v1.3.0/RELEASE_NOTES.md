# RootedOps v1.3.0

Release date: 2026-09-24

## Summary

Issue #8 Phase 3 adds lifecycle-aware employee payroll settlement. RootedOps now derives payment status from Salary Slip-linked Journal Entries, blocks active duplicates, and safely creates a new payment attempt after a prior JE has been cancelled.

## Added

- Payment status resolution for Not Recorded, Draft, Submitted, Cancelled, and conflicting active payment JEs.
- Stable logical payment key per Salary Slip plus unique sequential attempt keys.
- Migration backfill for existing Phase-2 payment JEs.
- Payroll Entry **Review Employee Payment Status** action.

## Changed

- Cancelled employee-payment JEs remain audit history but permit a subsequent replacement draft.
- Draft and submitted employee-payment JEs continue to block regeneration.
- A cancelled legacy consolidated employee-payment JE no longer prevents prospective employee-specific settlement.

## Component version

- `rootedops_payroll`: `0.2.0`

## Out of scope

- Payment transmission.
- ACH/NACHA generation.
- Historical accounting rewrites.
