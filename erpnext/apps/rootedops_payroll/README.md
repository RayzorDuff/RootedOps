### RootedOps Payroll

Payroll App for RootedOps

### Payroll reports

The app includes the standard ERPNext Script Report **Quarterly Payroll Tax Report**.

Filters:
- Company
- Year
- Quarter
- Salary Slip Status (`Submitted`, `Draft`, or `Draft and Submitted`)

The report provides quarter totals for Gross Pay, Federal Withholding, Colorado Withholding, employee Social Security, employee Medicare, Total Deductions, and Net Pay. Run it separately for each payroll company. For filed returns, use submitted Salary Slips unless a specific reconciliation requires draft records.

The report is installed or updated by:

```bash
bench --site erp.danks.store migrate
bench --site erp.danks.store clear-cache
```

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
