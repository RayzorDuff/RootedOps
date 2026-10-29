# Issue #6 — Payroll ACH / NACHA implementation

## Phase A — employee ACH destination configuration

RootedOps stores each ACH-paid employee's destination configuration on the ERPNext **Employee** record alongside the existing payroll payment method.

Fields added by RootedOps:

- Bank / credit union name
- Account type (`Checking` or `Savings`)
- Account-holder name, when different or useful operationally
- Routing number (`Password` field)
- Account number (`Password` field)
- ACH authorization active flag
- ACH authorization effective date

Routing and account numbers are Frappe `Password` fields. RootedOps operational helpers return masked values only; the unmasked values are available only to an internal server-side helper for future NACHA export. Do not copy full values into logs, issue comments, screenshots, test fixtures, or source control.

Validation covers:

- exactly 9 routing digits after removing spaces/hyphens;
- ABA routing check digit;
- checking/savings account type;
- account number present, alphanumeric, and no more than 17 characters;
- employee payroll payment method is `ACH`;
- payroll payment configuration is active;
- bank / credit union name is present;
- employee payroll payment configuration is active/effective for the payment date;
- ACH authorization has an effective date and is active/effective for the payment date.

No ACH file is generated in Phase A.

## ERPNext / High Plains sources of truth

Do not duplicate values that ERPNext already owns.

- Legal/company identity comes from ERPNext **Company**.
- Dank Mushrooms EIN comes from ERPNext `Company.tax_id` (shown as **Tax ID** in the UI).
- A later NACHA phase will normalize that EIN to nine digits and derive High Plains Bank's required Company ID as `1` + EIN.

High Plains Bank has stated that its NACHA import expects standard NACHA formatting with these known company requirements:

- Company Name: `DANK MUSHROOMS LLC` in uppercase, truncated only if the NACHA field requires it.
- Company ID: `1` followed by Dank Mushrooms' EIN.

The bank invited a generated test file for validation. Remaining originator/ODFI, effective-date, balanced/unbalanced, naming, and submission details remain configurable until confirmed through the test-file process.

## Phase B — NACHA originator profile

RootedOps adds a **RootedOps NACHA Profile** DocType to hold bank/origination parameters that ERPNext does not already own. The profile references ERPNext **Company** and **Bank Account** records; it does not duplicate the EIN or funding-account identity.

Derived values:

- legal/company name: ERPNext Company;
- NACHA company name: ERPNext Company name normalized to uppercase, with the 16-character Batch Header projection stored read-only for operator visibility;
- EIN: ERPNext `Company.tax_id`, normalized to exactly nine digits;
- High Plains Company ID: `1` + normalized EIN;
- employee payroll SEC code: `PPD`;
- payroll Company Entry Description: `PAYROLL`.

Profile-owned NACHA parameters:

- Bank Name;
- Funding Bank Account reference;
- Immediate Destination;
- Immediate Origin;
- Immediate Destination Name;
- Immediate Origin Name;
- Originating DFI Identification;
- balanced/unbalanced mode;
- optional Reference Code;
- optional output filename pattern;
- certification/readiness state.

Because High Plains has not yet supplied every origination value, a profile may be saved disabled with **Configuration Incomplete** status. RootedOps refuses to enable it or advance it to a testing/certification state until required values are present. This is deliberate: missing bank values remain explicit rather than being guessed.

Phase B still does not build or download a NACHA file. Phase C supplies the pure fixed-width NACHA formatter and control-total validation using synthetic data.
