### RootedOps Payroll

Payroll App for RootedOps

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

The **Payroll Tax Liability Reconciliation** report compares submitted Salary Slip liabilities with draft and submitted tax-payment Journal Entries for Federal Payroll Tax, Colorado Withholding, Colorado UI, and Colorado FAMLI. **Outstanding** subtracts only submitted payments; **After Drafts** also subtracts pending drafts for treasury planning and displays negative projected balances as overpayments. Draft and submitted Journal Entry references are shown separately as links. Its **Create Tax Payment Draft** action creates a tagged, balanced Bank Entry for the full quarterly liability and prevents a second non-cancelled draft for the same company, quarter, and tax type. **Link Existing Payment** safely tags an existing active Journal Entry after validating its company, obligation, and liability-account debit, so historical payments can be incorporated without database-console updates.

Payment drafts use the withholding bank account when one is configured, otherwise the default checking account. Review the bank and liability lines in ERPNext before submitting. Interest and penalties remain separate manual expense lines and are not included in the calculated tax liability.

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
