# RootedOps ERPNext Configuration Guide

This directory contains the ERPNext-specific configuration assets for RootedOps.

The focus of this folder is:

- Dank Mushrooms, LLC payroll and accounting
- Rooted Psyche accounting and future payroll
- employee attendance and hourly payroll automation
- supporting scripts that replace part of the earlier CSV/import workflow

This README is intentionally long-form. It is meant to preserve the state of the project after the CSV pack was first created and after the later bench-console work completed in ChatGPT.

---

# Current Status Summary

As of the latest update in this folder, the project has progressed through these phases:

## Phase 0 — Initial ERPNext configuration pack
Completed earlier.

Included:
- Companies
- Chart of Accounts CSVs
- Cost Centers
- Departments
- Designations
- Suppliers
- Projects
- Bank accounts template
- Asset categories
- Expense claim types
- Employee template

These files are still present and still useful.

## Phase 1 — Attendance foundation
Completed.

What was accomplished:
- Created and validated a `Day Shift`
- Enabled auto attendance
- Changed check-in/out interpretation to use explicit log type
- Created and submitted a `Shift Assignment`
- Confirmed clean `Employee Checkin` rows are converted into `Attendance`
- Confirmed `working_hours` is populated from check-in/check-out data

Result:
- Attendance is now a reliable source of hours worked.

## Phase 2 — Hourly payroll foundation
Completed.

What was accomplished:
- Switched Payroll Settings from leave-based payroll to attendance-based payroll
- Verified the stock ERPNext “payment days” model is not a good fit for an ad-hoc hourly employee
- Created a custom Python payroll automation approach
- Confirmed attendance-derived hours can be turned into:
  - gross pay
  - employee Social Security
  - employee Medicare
  - employer Social Security
  - employer Medicare
- Confirmed custom draft salary slip generation works from a script loaded into bench console

Result:
- The system now has a working scripted baseline for hourly payroll.

Confirmed diagnosis:
- The 204.09 net-pay result is explained by ERPNext still applying the submitted salary structure during salary-slip calculation.
- The test salary structure uses `Hourly Wage = 800.00` with `depends_on_payment_days = 1`.
- With 2 payment days out of a 7-day weekly period, ERPNext prorates that structure earning to 228.57.
- 228.57 - 19.84 Social Security - 4.64 Medicare = 204.09.
- In other words, the scripted attendance gross of 320.00 was not the value ultimately driving `net_pay`; the salary structure’s prorated earning was.

## Phase 3 — Federal and Colorado withholding automation
Not yet completed.

Next work:
- store employee W-4 / Colorado withholding inputs
- automate federal withholding from IRS Publication 15-T inputs
- automate Colorado withholding from DR 1098 / DR 0004 inputs
- wire those calculations into the custom payroll script

---

# Directory Contents

## CSV / import files

These files remain part of the project and are still useful for initial ERPNext setup:

| File | Purpose |
|---|---|
| `companies.csv` | Initial company import |
| `chart_of_accounts_dank_mushrooms_llc.csv` | Dank Mushrooms chart of accounts |
| `chart_of_accounts_rooted_psyche.csv` | Rooted Psyche chart of accounts |
| `cost_centers.csv` | Cost center import |
| `departments.csv` | Department import |
| `designations.csv` | Designation import |
| `employees_template.csv` | Employee import template |
| `bank_accounts_template.csv` | Bank account template |
| `suppliers.csv` | Supplier import |
| `projects.csv` | Project import |
| `expense_claim_types.csv` | Expense claim type import |
| `asset_categories.csv` | Asset category import |

## Scripts

These scripts were added after the initial CSV pack and represent the newer, bench-console-driven configuration work:

| Script | Purpose |
|---|---|
| `scripts/10_setup_master_data.py` | Idempotent creation of cost centers, departments, designations, and a payroll payable account structure outline |
| `scripts/20_setup_shift_and_test_employee.py` | Creates/updates Day Shift, Payroll Settings, test employee, and submitted Shift Assignment |
| `scripts/30_create_employee_home_page.py` | Creates the file-backed custom Desk page for the employee landing page |
| `scripts/40_setup_payroll_test_foundation.py` | Creates the clean test salary structure and assignment used during payroll testing |
| `scripts/50_hourly_payroll_automation.py` | Attendance-driven hourly payroll script with FICA calculations |
| `scripts/README_SCRIPTS.md` | Script usage notes and execution pattern |

## Handoff files

| File | Purpose |
|---|---|
| `CHATGPT_HANDOFF.md` | Full narrative handoff for a new ChatGPT session |
| `CHATGPT_HANDOFF.json` | Structured summary for quick reference |

---

# What still uses CSV imports vs. what is now better done by script

## Still best handled by CSV / importer
These are stable master-data imports and should remain as CSVs unless there is a strong reason to fully script them:

- companies
- chart of accounts
- suppliers
- projects
- asset categories
- expense claim types

## Now better handled by script
These were actively manipulated in the bench console during later troubleshooting and are now better represented by scripts:

- payroll settings
- shift setup
- shift assignment
- test employee creation / update
- salary structure cleanup and recreation
- attendance-driven payroll automation
- employee Desk page creation

---

# Reset ERPNext to a Clean State (Optional)

If ERPNext already has incorrect data and you want a real clean slate:

```bash
docker compose down
docker volume rm docker_erpnext_db_data
docker volume rm docker_erpnext_sites
docker volume rm docker_erpnext_apps
docker volume rm docker_erpnext_logs
docker compose up -d
```

Then re-bootstrap ERPNext and reapply the configuration.

---

# Initial Import Order (CSV-based bootstrap)

If starting from scratch in ERPNext and using the import files first, the baseline order remains:

1. `companies.csv`
2. Chart of Accounts (per company)
3. `cost_centers.csv`
4. `departments.csv`
5. `designations.csv`
6. `bank_accounts_template.csv`
7. `suppliers.csv`
8. `projects.csv`
9. `expense_claim_types.csv`
10. `asset_categories.csv`
11. `employees_template.csv`

After that baseline, the newer scripts in `scripts/` should be used to bring the environment to the current working state.

---

# Bench-console execution pattern for scripts

The scripts in `erpnext/scripts/` are intended to be loaded into bench console.

## Recommended pattern

From the project root on the host:

```bash
sudo docker cp erpnext/scripts/50_hourly_payroll_automation.py   erpnext-backend:/home/frappe/frappe-bench/sites/50_hourly_payroll_automation.py
```

Then open bench console:

```bash
sudo docker compose --env-file ./.env -f docker/docker-compose.yml exec erpnext-backend   bash -lc "bench --site erp.danks.store console"
```

Then load the script:

```python
exec(open("/home/frappe/frappe-bench/sites/50_hourly_payroll_automation.py").read(), globals())
```

This pattern was necessary because pasting large Python blocks directly into the terminal/console proved unreliable.

---

# Phase 1 Details — Attendance Foundation

The following was verified and/or corrected:

- `Employee`: `HR-EMP-00001`
- employee company: `Dank Mushrooms, LLC`
- employee default shift: `Day Shift`

## Shift Type
A `Day Shift` Shift Type was created and corrected to use:

- `enable_auto_attendance = 1`
- `determine_check_in_and_check_out = Strictly based on Log Type in Employee Checkin`
- `working_hours_calculation_based_on = First Check-in and Last Check-out`

## Shift Assignment
A submitted Shift Assignment was required. Default shift on Employee alone was not enough.

## Auto attendance behavior discovered
A key troubleshooting lesson:

`last_sync_of_checkin` must be set well past the end of the shift window for historical test data, otherwise `process_auto_attendance()` may not convert clean checkins into attendance rows.

The working test state used:

- `process_attendance_after = 2026-03-14`
- `last_sync_of_checkin = 2026-03-17 23:59:59`

## Working result
Attendance now shows:

- 2026-03-16 = Present, 8.0 hours
- 2026-03-17 = Present, 8.0 hours

This established the reliable foundation:

```text
Employee Checkin -> Attendance -> working_hours
```

---

# Phase 2 Details — Payroll Foundation

## Payroll Settings correction
The original Payroll Settings were wrong for this use case:

- `payroll_based_on = Leave`
- `consider_unmarked_attendance_as = Present`

This produced incorrect salary slips.

The working settings are now:

- `payroll_based_on = Attendance`
- `consider_unmarked_attendance_as = Absent`

## Stock ERPNext salary behavior that was tested and rejected
A weekly salary structure was created and successfully generated a salary slip, but it used the stock “payment days” model.

That resulted in proration like:

```text
800 * 2 / 7 = 228.57
```

That model is wrong for this employee because:

- the employee is hourly
- the schedule is ad-hoc
- weekends may be worked
- the goal is true hours-worked pay, not fixed weekly salary prorated by attendance days

## New payroll design
The chosen design is:

```text
Attendance -> hours -> gross pay from hourly rate
          -> employee FICA deductions
          -> employer FICA tracking
          -> future federal withholding
          -> future Colorado withholding
          -> net pay
```

## What is now automated
The custom hourly payroll script currently handles:

- attendance hour summation
- gross pay from `hours * hourly_rate`
- employee Social Security
- employee Medicare
- employer Social Security
- employer Medicare
- draft salary slip rebuilding

## Current compliance boundary
As of this phase, the script automates FICA only.

Still to be implemented:
- federal withholding from W-4 inputs and IRS 15-T logic
- Colorado withholding from W-4 / DR 0004 inputs and Colorado rules

---

# Custom Employee Desk Page

Because the ERPNext v16 Workspace UI was inconsistent, a file-backed custom Desk page was created as a working employee landing page.

Working URLs:

- `https://erp.danks.store/desk/employee-home`
- `https://erp.danks.store/app/employee-home`

The page assets live inside the container/app path:

```text
apps/hrms/hrms/hr/page/employee_home
```

This is not managed by the CSV files. It is created by script.

---

# Payroll Compliance Notes

## FICA
The script currently uses 2026 FICA rates:

- Social Security employee = 6.2%
- Social Security employer = 6.2%
- Medicare employee = 1.45%
- Medicare employer = 1.45%
- Social Security wage base = 184,500 for 2026

## Federal withholding
Planned approach:
- store the employee’s W-4 inputs
- compute withholding from those stored values
- only revisit when:
  - employee submits a new W-4
  - or the tax year changes

## Colorado withholding
Planned approach:
- store Colorado withholding inputs
- compute withholding from those stored values
- only revisit when:
  - employee changes Colorado withholding setup
  - or the tax year changes

This matches the intended real-world workflow better than manual per-pay-cycle calculation.

---

# Recommended next steps

## Immediate next phase
Implement withholding automation:

1. create employee tax profile data structure
2. implement federal withholding calculation
3. implement Colorado withholding calculation
4. integrate those into the payroll script
5. create liability accounts and posting structure

## After that
1. clean up salary component/account mappings
2. finalize the payroll payable and withholding accounts
3. create a “first real employee” setup script
4. update documentation again

---

# Important project note

The `Shift Type` list issue turned out to be caused by a UI filter. The shift itself was valid the whole time.

That is an example of why the newer scripts are valuable: they document the *actual* working backend state independent of the UI.

---

# See also

- `scripts/README_SCRIPTS.md`
