### RootedOps Payroll

Payroll App for RootedOps


## Employee payroll payment configuration (Issue #8, Phase 1)

RootedOps installs a payment-configuration foundation on **Employee** for future
employee-specific payroll settlement. This phase does **not** create or submit
payment Journal Entries. It records only the payment method, whether the
configuration is active, an optional effective date, and non-sensitive operator
instructions. Supported methods are `ACH`, `Venmo`, `Apple Pay / Apple Cash`,
`Paper Check`, and `Other / Manual`.

ACH routing and account numbers are intentionally **not** part of these fields.
They will be added later with protected storage as part of Issue #6. Never place
ACH credentials in **Payroll Payment Instructions**.

The migration also reserves read-only Journal Entry linkage fields for the later
employee-payment service: Employee, Salary Slip, Payroll Entry, payment method,
and a unique stable payment key. Phase 1 does not populate those Journal Entry
fields; they exist now so subsequent phases can add payment creation without
changing the metadata contract.

### Payroll reports

The app includes the standard ERPNext Script Report **Quarterly Payroll Tax Report**.

Filters:
- Company
- Year
- Quarter
- Salary Slip Status (`Submitted`, `Draft`, or `Draft and Submitted`)

The report provides quarter totals for Gross Pay, Federal Withholding, Colorado Withholding, Colorado FAMLI, employee and employer FICA, Colorado UI gross/excess/taxable wages, Colorado UI premium, employer taxes, Total Deductions, and Net Pay. Run it separately for each payroll company. For filed returns, use submitted Salary Slips unless a specific reconciliation requires draft records.

### Colorado unemployment insurance

Colorado UI is an employer-paid payroll tax. It is accrued in the consolidated payroll Journal Entry through the existing Payroll Tax Expense and Payroll Tax Payable accounts and is included in the tax-reserve transfer amount. It does not appear as an employee deduction on Salary Slips.

After migration, configure each Colorado employer in **Company → Colorado Unemployment Insurance**:

- Accrue Colorado UI: enabled
- Colorado UI Employer Account
- Colorado UI Total Rate (%), such as `3.05`
- Colorado UI Annual Wage Base, such as `30600`
- Colorado UI Effective Date

The rate field stores the total rate shown by CDLE. The payroll engine applies it to employee wages up to the annual wage base and tracks excess wages separately.

## Colorado FAMLI (2026)

RootedOps can withhold the employee FAMLI premium, accrue any employer premium, add both amounts to the payroll tax reserve, and show them on the Salary Slip, payroll previews, journal-entry previews, and Quarterly Payroll Tax Report.

For a Colorado employer with nine or fewer employees using the state plan, enable FAMLI on Company with an employee rate of `0.44`, employer rate of `0`, annual wage base of `184500`, and effective date `2026-01-01`. Leave **Employer Pays Employee FAMLI Share** unchecked unless the company intentionally absorbs the employee premium.

The rates and wage base are Company settings because FAMLI rates and the federal Social Security wage base can change by calendar year. Previously submitted Salary Slips are not rewritten automatically; reconcile any pre-installation payroll separately before filing.

The report is installed or updated by:

```bash
bench --site erp.danks.store migrate
bench --site erp.danks.store clear-cache
```

## Payroll tax liability reconciliation

The **Payroll Tax Liability Reconciliation** report compares submitted Salary Slip liabilities with draft and submitted tax-payment Journal Entries for Federal Payroll Tax, Colorado Withholding, Colorado UI, and Colorado FAMLI. **Outstanding** subtracts only submitted payments; **After Drafts** also subtracts pending drafts for treasury planning and displays negative projected balances as overpayments. Draft and submitted Journal Entry references are shown separately as links. Its **Create Tax Payment Draft** action creates a tagged, balanced Bank Entry for the full quarterly liability and prevents a second non-cancelled draft for the same company, quarter, and tax type. **Link Existing Payment** safely tags an existing active Journal Entry after validating its company, obligation, and liability-account debit, so historical payments can be incorporated without database-console updates. **Record Filing Confirmation** stores the filing status, date, confirmation number, and uploaded receipt on the linked Journal Entry without changing its accounting lines.

Payment drafts use the withholding bank account when one is configured, otherwise the default checking account. Review the bank and liability lines in ERPNext before submitting. Interest and penalties remain separate manual expense lines and are not included in the calculated tax liability.

## Plaid historical bank-transaction staging

RootedOps includes a controlled Plaid historical utility for the 2026 bank-history backfill. Its staging/inspection phase creates a temporary Hosted Link Item with a 730-day Transactions request, verifies the existing production Item remains unchanged, waits for Plaid to report the historical pull complete, maps candidate accounts to the canonical ERPNext Bank Accounts, and produces a private deduplication dry run with **zero financial writes**. A separate deterministic prepare/commit gate can then create only reviewed historical native `Bank Transaction` records; it also handles the ERPNext/MariaDB case-insensitive `transaction_id` UNIQUE-index edge case without merging distinct Plaid IDs. It never creates accounting vouchers or performs reconciliation. Operator commands, rollback behavior, verification, receipts, and cleanup procedures are documented in `erpnext/README_SCRIPTS.md`.

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench install-app rootedops_payroll
```

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/rootedops_payroll
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### License

gpl-3.0


### Split-shift checkins

Standard-hourly payroll treats explicit Employee Checkin `IN` → `OUT` pairs as the
authoritative source for paid hours whenever checkins exist in the payroll
period. This avoids overstating a day when an employee clocks out and later
clocks back in: the unpaid gap between sessions is not paid.

ERPNext `Day Shift` should also use **Every Valid Check-in and Check-out** for its
Attendance working-hours calculation so the Attendance UI agrees with payroll.
RootedOps reports a diagnostic warning when Attendance hours and paired-checkin
hours differ, and blocks payroll when the checkin sequence itself is malformed
(for example, an unmatched `IN` or `OUT`).

### Payroll Event Cost Report

`Payroll Event Cost Report` is a read-only evidentiary / reconciliation report for a specific
nanny or hourly-payroll event window. Select Company, Employee, Event Start, and Event End.
The report reads Employee Checkin IN/OUT sessions, applies the employee's RootedOps pay model
(including the hybrid 22:00-06:00 overnight flat when configured), and shows:

- each compensated hourly or overnight-flat segment,
- gross wages,
- employer Social Security and Medicare,
- Colorado unemployment insurance,
- employer Colorado FAMLI, and
- total employer payroll expense.

The report deliberately does not allocate federal or Colorado income-tax withholding to a
partial event window because those are employee deductions calculated on the complete payroll
period. It does not create or modify Salary Slips or Journal Entries.
## Employee-specific payroll payment drafts (Issue #8 Phase 2)

The Payroll Entry **Create Employee Payment Draft JEs** action now creates one draft Bank Entry Journal Entry per submitted, positive-net-pay Salary Slip instead of one consolidated employee-payment JE. The service preflights the complete batch before inserting any Journal Entries, requires an active/effective Employee payroll payment configuration, preserves Employee/Salary Slip/Payroll Entry/payment-method metadata, and refuses duplicates for a Salary Slip.

The debit clears Payroll Payable with the Employee as party and the credit uses the configured/default company checking Bank GL account. Payroll accrual, withholding-reserve transfers, and tax-remittance accounting remain consolidated and unchanged. Existing legacy consolidated employee-payment JEs are not rewritten; a populated legacy Payroll Entry payment-JE link blocks the new employee-specific action to avoid double settlement.

Phase 2 creates **draft accounting records only**. It does not execute ACH, Venmo, Apple Cash, or check payments, and cancellation/amendment lifecycle handling is reserved for the next phase.
