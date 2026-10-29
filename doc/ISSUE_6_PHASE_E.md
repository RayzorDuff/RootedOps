# Issue #6 — Phase E: NACHA Payroll Export

Phase E adds the validated export boundary between finalized ERPNext
payroll and a downloadable NACHA payroll file.

## Scope

- Accept only a submitted/finalized Payroll Entry.
- Resolve submitted Salary Slips and use Salary Slip net pay as the source of truth.
- Include only employees whose effective payroll payment method is ACH.
- Exclude other payment methods and show them in the export summary.
- Validate the enabled NACHA profile, company match, required originator fields,
  effective date, ACH credentials, and unbalanced balance mode.
- Generate the NACHA file using the Phase C formatter.
- Validate the generated file before returning it.
- Record non-sensitive export audit metadata and a SHA-256 file hash.
- Download the validated `.ach` file.

## Security

Employee routing and account numbers are used only during server-side export
construction. They are not written to source-controlled fixtures, logs, or the
export audit record. The raw generated NACHA file is not retained by the Phase E
audit record.

## Export versioning

Each Payroll Entry receives an independent export version sequence. A later
generation creates a new export record and filename rather than silently
replacing an earlier export.

## Test mode

A profile with certification status `Ready for Bank Test` is exported as
`Test` mode. This does not transmit the file anywhere.

## Balance mode

Phase E currently permits only an explicitly configured `Unbalanced` profile.
Balanced/offset generation remains deferred until the bank's specification
defines the required funding-account and offset-entry behavior.

## Current controlled test

The intended first end-to-end test is Payroll Entry `HR-PRUN-2026-00054`
with Corben's `$84.78` net pay as the sole ACH employee. Robert Weber's
`$287.14` is excluded because his payment method is not ACH.

The test must use synthetic/bank-test originator and employee account values.
No bank transmission is performed by RootedOps.

## Operational note

Generating a NACHA file does not create or submit a payroll payment Journal
Entry. Accounting settlement remains a separate workflow.
