# RootedOps v1.4.2

Release date: 2026-09-25

## Issue #6 — ACH Phase B

This patch release adds the NACHA originator/profile configuration boundary without generating ACH files or changing payroll accounting.

### Added

- `RootedOps NACHA Profile` DocType linking ERPNext Company and funding Bank Account to NACHA-specific origination parameters.
- ERPNext-derived NACHA company identity: uppercase company name, 16-character Batch Header projection, and Company ID `1` + the normalized EIN from `Company.tax_id`.
- Payroll constants for SEC `PPD` and Company Entry Description `PAYROLL`.
- Explicit balanced/unbalanced/unconfirmed mode and bank-certification status.
- Readiness validation that prevents incomplete profiles from being enabled or advanced to testing/certification states.
- Tests for company identity and profile structural validation.

### Configuration boundary

ERPNext remains authoritative for Company identity, Company Tax ID/EIN, and Bank Account identity. RootedOps stores only NACHA-specific values that ERPNext does not already own.

High Plains values that have not yet been supplied remain blank and explicit; RootedOps does not invent Immediate Destination, Immediate Origin, ODFI Identification, or balance mode.

### Notes

- No NACHA file generation is included in this phase.
- No Git tag is created because this is an incremental phase of open Issue #6.
