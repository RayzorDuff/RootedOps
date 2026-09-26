# RootedOps 1.4.5 — Issue #6 Phase E

Adds validated payroll NACHA export and audit metadata.

- Payroll Entry → ACH-only employee selection
- Salary Slip net-pay reconciliation
- NACHA generation and structural/control validation
- 94-character / 10-record blocking
- Export audit record with file hash
- Downloadable `.ach` test artifact
- Synthetic-data automated coverage

Balanced/offset NACHA and bank transmission remain out of scope pending the bank's specification/certification requirements.
