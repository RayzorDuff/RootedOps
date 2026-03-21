# RootedOps ERPNext Configuration Guide

This directory contains the ERPNext-specific configuration assets for RootedOps.

Primary focus:
- Dank Mushrooms, LLC payroll and accounting
- Rooted Psyche accounting and future payroll
- employee attendance and hourly payroll support
- ERPNext configuration assets that combine CSV imports and bench-console scripts

This README is the high-level configuration guide. Script-specific operating details, bench-console usage, and payroll automation maintenance notes now live in `scripts/README_SCRIPTS.md`.

---

# Current Status Summary

## Phase 0 — Initial ERPNext configuration pack
Completed earlier.

Included:
- companies
- chart of accounts CSVs
- cost centers
- departments
- designations
- suppliers
- projects
- bank accounts template
- asset categories
- expense claim types
- employee template

These files remain useful for initial setup and rebuilds.

## Phase 1 — Attendance foundation
Completed.

Accomplished:
- created and validated `Day Shift`
- enabled auto attendance
- changed check-in/out interpretation to use explicit log type
- created and submitted a `Shift Assignment`
- confirmed clean `Employee Checkin` rows convert into `Attendance`
- confirmed `working_hours` is populated from check-in/check-out data

Result:
- Attendance is now a reliable source of hours worked.

## Phase 2 — Hourly payroll foundation
Completed.

Accomplished:
- switched Payroll Settings from leave-based payroll to attendance-based payroll
- verified the stock ERPNext payment-days model is not a good fit for this ad-hoc hourly employee
- created a custom Python payroll automation approach
- confirmed attendance-derived hours can be turned into gross pay plus employee/employer FICA
- confirmed custom draft salary slip generation works from a script loaded into bench console

Result:
- The system has a working scripted baseline for hourly payroll.

## Phase 3 — Withholding automation, employee tax profiles, and Journal Entry draft creation
Completed.

Accomplished:
- resolved the original `204.09` net-pay issue caused by ERPNext salary-structure recalculation
- added federal withholding for 2026 weekly payroll
- added Colorado withholding for 2026
- added persistent employee tax-profile storage on Employee custom fields
- added persistent employee hourly-rate storage on Employee custom fields
- added payroll liability summary generation
- added payroll register output for a single slip
- added Journal Entry preview generation
- added successful Journal Entry draft creation using cleaned-up payroll account mapping

Result:
- A full single-employee payroll calculation now works end to end through a draft Salary Slip and a draft Journal Entry.

---


## Phase 4 — Batch payroll-period runs and consolidated Journal Entry foundation
Working and validated through a three-employee payroll batch.

Accomplished so far:
- added batched payroll-period helpers to `scripts/50_hourly_payroll_automation.py`
- added consolidated payroll register output
- added consolidated liability summary output
- added consolidated Journal Entry preview generation
- added draft consolidated Journal Entry creation support
- preserved the existing single-slip workflow for isolated testing
- validated a clean three-employee payroll run after fixing attendance preprocessing and stored payroll profile values
- hardened payroll diagnostics so zero-hour attendance and `skip_auto_attendance = 1` checkins are surfaced immediately

# Latest Verified Working State

## Test employee
- Employee: `HR-EMP-00001`
- Company: `Dank Mushrooms, LLC`
- Hourly rate stored on Employee: `20.00`

## Verified attendance
- 2026-03-16 = Present, 8.0 hours
- 2026-03-17 = Present, 8.0 hours

## Verified payroll calculation for period `2026-03-15` to `2026-03-21`
- Hours: `16.0`
- Gross: `320.00`
- Employee Social Security: `19.84`
- Employee Medicare: `4.64`
- Federal withholding: `1.00`
- Colorado withholding: `9.43`
- Employer Social Security: `19.84`
- Employer Medicare: `4.64`
- Net pay: `285.09`

## Verified liability summary
- Gross wages: `320.00`
- Employee tax total: `34.91`
- Employer tax total: `24.48`
- Total payroll expense: `344.48`
- Total liability before cash: `59.39`

## Verified payroll accounts / company configuration
Validated accounts:
- `Payroll Expense - DML`
- `Payroll Tax Expense - DML`
- `Payroll Payable - DML`
- `Payroll Tax Payable - DML`
- `Payroll Withholding Payable - DML`

Validated company field:
- `Company("Dank Mushrooms, LLC").default_payroll_payable_account = "Payroll Payable - DML"`

## Verified Journal Entry preview / draft creation
Resolved mapping:
- `Payroll Expense - DML` → gross wages expense
- `Payroll Tax Expense - DML` → employer payroll tax expense
- `Payroll Payable - DML` → net payroll payable to employee
- `Payroll Tax Payable - DML` → Social Security and Medicare payable
- `Payroll Withholding Payable - DML` → federal and Colorado withholding payable

Verified JE preview:
- total debit: `344.48`
- total credit: `344.48`
- balanced: yes

Verified JE drafting:
- a draft Journal Entry was successfully created
- unsupported `reference_type="Salary Slip"` values were removed from JE rows and replaced with `user_remark` linkage

---

# Directory Contents

## CSV / import files
These remain useful for initial ERPNext setup:

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
These scripts now handle the active ERPNext configuration and payroll workflow:

| Script | Purpose |
|---|---|
| `scripts/10_setup_master_data.py` | Creates/updates cost centers, departments, designations, and helper master data |
| `scripts/20_setup_shift_and_test_employee.py` | Creates/updates Day Shift, Payroll Settings, test employee, and submitted Shift Assignment |
| `scripts/21_create_employee.py` | Creates or updates a payroll-test employee, linked User, optional payroll custom fields, and submitted Shift Assignment |
| `scripts/30_create_employee_home_page.py` | Creates the file-backed custom Desk page for the employee landing page |
| `scripts/40_setup_payroll_test_foundation.py` | Creates/repairs the test salary structure and assignment |
| `scripts/50_hourly_payroll_automation.py` | Attendance-driven hourly payroll with FICA, withholding, employee tax profiles, single-slip and batched payroll runs, consolidated register output, JE preview, and draft JE creation |
| `scripts/README_SCRIPTS.md` | Script usage notes, payroll automation details, maintenance procedures, and validation steps |

## Handoff files
| File | Purpose |
|---|---|
| `CHATGPT_HANDOFF.md` | Narrative handoff for a new ChatGPT session |
| `CHATGPT_HANDOFF.json` | Structured handoff summary |

---

# What still uses CSV imports vs. what is now better done by script

## Still best handled by CSV / importer
- companies
- chart of accounts
- suppliers
- projects
- asset categories
- expense claim types

## Now better handled by script
- payroll settings
- shift setup
- shift assignment
- test employee creation / update
- creation of additional payroll-test employees for multi-employee batch testing
- salary structure cleanup and recreation
- attendance-driven payroll automation
- employee payroll tax profile storage
- employee Desk page creation
- payroll liability summary / JE preview / draft JE creation
- batched payroll-period runs with one consolidated Journal Entry preview/draft

---

# Payroll accounting design currently in use

For Phase 3, the accounting model now assumes:
- wages expense booked to `Payroll Expense - DML`
- employer payroll tax expense booked to `Payroll Tax Expense - DML`
- net wages credited to `Payroll Payable - DML`
- Social Security and Medicare credited to `Payroll Tax Payable - DML`
- federal and Colorado withholding credited to `Payroll Withholding Payable - DML`

This should be treated as the working baseline for future payroll phases.

---

# Custom Employee Desk Page

Because the ERPNext v16 Workspace UI was inconsistent, a file-backed custom Desk page was created as a working employee landing page.

Working URLs:
- `https://erp.danks.store/desk/employee-home`
- `https://erp.danks.store/app/employee-home`

The page assets live in:

```text
apps/hrms/hrms/hr/page/employee_home
```

This page is script-managed rather than CSV-managed.

---

# Immediate Next Phase

## Phase 4 — Payroll batching and operationalization
Recommended next work:
1. batch multiple salary slips into one payroll-period run
2. create consolidated payroll register output
3. create one consolidated Journal Entry for a payroll period
4. decide whether to introduce Payroll Entry objects or stay on the custom scripted path
5. add stronger validation and reconciliation helpers
6. document a first real employee onboarding procedure using actual W-4 and Colorado inputs

---

# Suggested opening request for the next ChatGPT session

"""
Continue RootedOps ERPNext payroll Phase 4. Phase 4 batching basics are now implemented in `erpnext/scripts/50_hourly_payroll_automation.py`, including `run_batched_hourly_payroll()`, consolidated register output, and consolidated Journal Entry preview/draft creation. Review `erpnext/CHATGPT_HANDOFF.md`, `erpnext/CHATGPT_HANDOFF.json`, `erpnext/README.md`, `erpnext/scripts/README_SCRIPTS.md`, and `erpnext/scripts/50_hourly_payroll_automation.py`. Next, harden the payroll-period workflow with reconciliation checks, duplicate-run safeguards, and an operator checklist.
"""


## Payroll-ready employee onboarding for hourly payroll

Use `erpnext/scripts/21_create_employee.py` for test or scripted onboarding. The employee must have a submitted Shift Assignment, a submitted Salary Structure Assignment, and RootedOps payroll custom fields populated. `erpnext/scripts/50_hourly_payroll_automation.py` now processes auto attendance first by default during batch runs, but the safest operational pattern is still: create employee -> add checkins -> confirm attendance -> run payroll batch.


# Latest multi-employee validation

## Verified three-employee payroll calculation for period `2026-03-15` to `2026-03-21`
- `HR-EMP-00001` gross `400.00`, net `347.45`
- `HR-EMP-00002` gross `472.50`, net `403.96`
- `HR-EMP-00003` gross `258.75`, net `232.23`

This confirms:
- attendance-based hourly payroll works across multiple employees
- stored employee payroll profile values are read from Employee custom fields
- one payroll-period batch can rebuild multiple draft Salary Slips
- one consolidated Journal Entry preview can summarize the payroll period

## Known operational caveats now documented
- Historical employees created before the patched `21_create_employee.py` may need payroll-field backfill.
- Test or imported `Employee Checkin` rows with `skip_auto_attendance = 1` will be ignored by auto attendance.
- If checkins change after attendance is already submitted, cancel/delete and regenerate the affected Attendance rows before rerunning payroll.

# Clean steps to create a fourth employee and test the batch

## 1. Load the employee helper
```python
exec(open("/home/frappe/frappe-bench/sites/21_create_employee.py").read(), globals())
```

## 2. Create employee 4 as payroll-ready from the start
```python
result = create_or_update_employee(
    employee_name="Payroll Test Employee 4",
    first_name="Payroll",
    last_name="Employee 4",
    user_email="payroll.test4@example.com",
    company="Dank Mushrooms, LLC",
    department="Operations - DML",
    designation="Cultivation Technician",
    default_shift="Day Shift",
    shift_assignment_start_date="2026-03-15",
    hourly_rate=24.00,
    salary_structure="Dank Mushrooms Weekly Test",
    salary_structure_assignment_start_date="2026-03-15",
    salary_structure_base=800.0,
    create_salary_structure_assignment=True,
    federal_profile={
        "filing_status": "Single",
        "step2_checked": 0,
        "step3_annual_credits": 0.0,
        "step4a_other_income": 0.0,
        "step4b_deductions": 0.0,
        "step4c_extra_withholding": 0.0,
        "exempt": 0,
    },
    colorado_profile={
        "filing_status": "Single",
        "dr0004_line2": None,
        "dr0004_line2_override": 0,
        "dr0004_line3": 0.0,
        "exempt": 0,
    },
)
result
```

## 3. Insert clean test checkins with auto attendance enabled
```python
insert_checkin_pair("HR-EMP-00004", "2026-03-16 09:00:00", "2026-03-16 13:00:00")
insert_checkin_pair("HR-EMP-00004", "2026-03-17 10:00:00", "2026-03-17 15:30:00")
insert_checkin_pair("HR-EMP-00004", "2026-03-18 08:30:00", "2026-03-18 12:30:00")
```

## 4. Process auto attendance and verify hours
```python
shift = frappe.get_doc("Shift Type", "Day Shift")
shift.process_auto_attendance()
frappe.db.commit()

frappe.get_all(
    "Attendance",
    filters={
        "employee": "HR-EMP-00004",
        "attendance_date": ["between", ["2026-03-15", "2026-03-21"]],
    },
    fields=["name", "attendance_date", "status", "working_hours", "docstatus"],
    order_by="attendance_date asc",
)
```

## 5. Run the four-employee payroll batch
```python
exec(open("/home/frappe/frappe-bench/sites/50_hourly_payroll_automation.py").read(), globals())

batch = run_batched_hourly_payroll(
    employees=["HR-EMP-00001", "HR-EMP-00002", "HR-EMP-00003", "HR-EMP-00004"],
    start_date="2026-03-15",
    end_date="2026-03-21",
    company="Dank Mushrooms, LLC",
)
```

## 6. Verify the result
```python
batch["salary_slip_names"]
preview = batch["consolidated_journal_entry_preview"]
preview["employee_count"], preview["is_balanced"]
preview["liability_summary"]

for slip_name in batch["salary_slip_names"]:
    slip = frappe.get_doc("Salary Slip", slip_name)
    print("
", slip.name, slip.employee)
    print("Gross:", slip.gross_pay)
    print("Net:", slip.net_pay)
```
