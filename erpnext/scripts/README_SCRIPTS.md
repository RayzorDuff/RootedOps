# RootedOps ERPNext Scripts

These scripts are intended to be loaded into `bench --site erp.danks.store console`.

This README is the script-operations guide. It documents:
- how to load and run the scripts
- what each script currently does
- the verified payroll automation workflow in `50_hourly_payroll_automation.py`
- annual and employee-change maintenance procedures
- validation steps before using the process for a real employee

---

# General bench-console pattern

Copy the script into the ERPNext container:

```bash
sudo docker cp erpnext/scripts/<scriptname>.py \
  erpnext-backend:/home/frappe/frappe-bench/sites/<scriptname>.py
```

Open bench console:

```bash
sudo docker compose --env-file ./.env -f docker/docker-compose.yml exec erpnext-backend \
  bash -lc "bench --site erp.danks.store console"
```

Load the file:

```python
exec(open("/home/frappe/frappe-bench/sites/<scriptname>.py").read(), globals())
```

This pattern is preferred because pasting large Python blocks directly into bench console proved unreliable.

---

# Script purposes

## `10_setup_master_data.py`
Creates or updates:
- payroll-related cost centers
- departments
- designations
- helper accounts if they already exist in the company chart structure

## `20_setup_shift_and_test_employee.py`
Creates or updates:
- Payroll Settings
- Day Shift
- test employee
- submitted Shift Assignment
- clean test checkins (optional helper)

## `21_create_employee.py`
Creates or updates a payroll-test employee with configurable values:
- linked User record
- Employee master record
- default shift
- submitted Shift Assignment
- hourly rate custom field
- optional federal and Colorado withholding profile custom fields
- optional submitted Salary Structure Assignment
- helper to backfill payroll setup for older employees created before this script was patched
- helper to create IN/OUT Employee Checkin pairs with `skip_auto_attendance = 0`

Use this before multi-employee payroll testing and payroll-ready onboarding so each employee is created consistently for the scripted payroll flow.

## `30_create_employee_home_page.py`
Creates the file-backed Desk page:
- `employee-home`
- assets under `apps/hrms/hrms/hr/page/employee_home`

## `40_setup_payroll_test_foundation.py`
Creates or repairs:
- test salary structure
- test salary structure assignment

## `50_hourly_payroll_automation.py`
Provides:
- attendance-driven hourly payroll helper
- employee FICA
- employer FICA
- federal withholding for 2026 weekly payroll
- Colorado withholding for 2026
- employee tax-profile custom fields on Employee
- stored employee hourly rate
- draft salary slip rebuilding
- payroll liability summary
- payroll register row output
- Journal Entry preview generation
- draft Journal Entry creation
- batched payroll-period runs
- consolidated payroll register output
- consolidated Journal Entry preview and draft creation

---

# Verified Phase 3 payroll workflow in `50_hourly_payroll_automation.py`

## Root cause that was resolved
The original incorrect `204.09` net pay was caused by ERPNext still applying submitted Salary Structure math during Salary Slip validation and recalculation.

The script was reworked so the custom hourly path now:
- persists intended earnings and deductions
- bypasses the stock salary-structure recalculation path for this use case
- normalizes saved child-row flags so `depends_on_payment_days = 0`

## Current test result
Verified pay period: `2026-03-15` to `2026-03-21`

Verified output:
- hours: `16.0`
- gross: `320.00`
- employee Social Security: `19.84`
- employee Medicare: `4.64`
- federal withholding: `1.00`
- Colorado withholding: `9.43`
- employer Social Security: `19.84`
- employer Medicare: `4.64`
- net pay: `285.09`

## Verified liability / JE result
- gross wages: `320.00`
- employee tax total: `34.91`
- employer tax total: `24.48`
- total payroll expense: `344.48`
- JE preview balanced at `344.48` debit / `344.48` credit
- draft Journal Entry creation
- batched payroll-period runs
- consolidated payroll register output
- consolidated Journal Entry preview and draft creation succeeded
- clean four-employee batch validation completed successfully

---

# Employee tax-profile custom fields used by the script

## Federal
- `rootedops_federal_filing_status`
- `rootedops_federal_step2_checked`
- `rootedops_federal_step3_annual_credits`
- `rootedops_federal_step4a_other_income`
- `rootedops_federal_step4b_deductions`
- `rootedops_federal_step4c_extra_withholding`
- `rootedops_federal_exempt`

## Colorado
- `rootedops_colorado_filing_status`
- `rootedops_colorado_dr0004_line2_override`
- `rootedops_colorado_dr0004_line2`
- `rootedops_colorado_dr0004_line3`
- `rootedops_colorado_exempt`

## Other
- `rootedops_hourly_rate`

Important note:
- Colorado line 2 uses a separate override checkbox because the numeric field may not be nullable in this ERPNext environment.
- `dr0004_line2_override = 0` means use the default Colorado subtraction amount.
- `dr0004_line2_override = 1` means use the stored `dr0004_line2` value.

---

# Typical usage for `50_hourly_payroll_automation.py`

## 1. Load the script
```python
exec(open("/home/frappe/frappe-bench/sites/50_hourly_payroll_automation.py").read(), globals())
```

## 2. Ensure Employee tax-profile fields exist and seed the test employee
```python
ensure_employee_tax_profile_custom_fields()
seed_test_employee_tax_profile()
get_employee_tax_profile("HR-EMP-00001")
```

## 3. Rebuild hourly salary slip using stored employee values
```python
result = rebuild_hourly_salary_slip(
    employee="HR-EMP-00001",
    start_date="2026-03-15",
    end_date="2026-03-21",
)
```

## 4. Inspect the result
```python
result["gross"]
result["net_pay"]
result["liability_summary"]
result["journal_entry_preview"]
```

## 5. Create draft Journal Entry
```python
create_payroll_journal_entry_draft(result)
```

---

## 6. Run a batched payroll period and inspect the consolidated outputs
```python
batch = run_batched_hourly_payroll(
    employees=["HR-EMP-00001"],
    start_date="2026-03-15",
    end_date="2026-03-21",
    company="Dank Mushrooms, LLC",
)

batch["salary_slip_names"]
batch["consolidated_register"]
batch["consolidated_liability_summary"]
batch["consolidated_journal_entry_preview"]
```

## 7. Optionally create one consolidated draft Journal Entry for the payroll period
```python
run_batched_hourly_payroll(
    employees=["HR-EMP-00001"],
    start_date="2026-03-15",
    end_date="2026-03-21",
    company="Dank Mushrooms, LLC",
    create_consolidated_journal_entry=True,
)
```

## 8. Optional attendance-driven employee discovery helper
```python
get_employees_with_attendance_in_period(
    start_date="2026-03-15",
    end_date="2026-03-21",
    company="Dank Mushrooms, LLC",
)
```

---

# Phase 4 batching notes

The new batched-payroll path is designed to keep the existing single-slip helper intact while adding a payroll-period wrapper around it.

Key functions:
- `get_employees_with_attendance_in_period(start_date, end_date, company=None)`
- `build_consolidated_payroll_register(payroll_results)`
- `summarize_consolidated_payroll_liabilities(payroll_results)`
- `build_consolidated_payroll_journal_entry_preview(payroll_results, ...)`
- `create_consolidated_payroll_journal_entry_draft(payroll_results, ...)`
- `run_batched_hourly_payroll(employees, start_date, end_date, ...)`

Behavior notes:
- the batched run still creates or refreshes one Salary Slip per employee for the pay period
- the consolidated Journal Entry preview rolls those slips into one combined accrual entry
- JE lines are aggregated by account + cost center so multiple employees can still preserve cost-center separation
- all slips in one consolidated run must belong to a single company
- the existing single-slip helpers remain available for debugging and employee-level review

---

# Payroll account model now assumed by the script

The current Journal Entry mapping expects these accounts to exist and remain available:
- `Payroll Expense - DML`
- `Payroll Tax Expense - DML`
- `Payroll Payable - DML`
- `Payroll Tax Payable - DML`
- `Payroll Withholding Payable - DML`

The current mapping behavior is:
- gross wages → `Payroll Expense - DML`
- employer payroll tax expense → `Payroll Tax Expense - DML`
- net payroll payable → `Payroll Payable - DML`
- Social Security and Medicare payable → `Payroll Tax Payable - DML`
- federal and Colorado withholding payable → `Payroll Withholding Payable - DML`

Verified company default:
```python
frappe.get_doc("Company", "Dank Mushrooms, LLC").default_payroll_payable_account
```
Expected:
```python
'Payroll Payable - DML'
```

---

# Important implementation notes

## Attendance foundation requirements
The payroll script assumes attendance is already working correctly.

That means:
- `Day Shift` exists
- auto attendance is enabled
- checkin interpretation is strictly based on log type
- Shift Assignment is submitted
- Attendance rows are submitted and have `working_hours`

## Journal Entry row linkage
A first JE draft attempt failed because this ERPNext environment does not allow `reference_type = "Salary Slip"` on Journal Entry Account rows.

The working implementation therefore does **not** set:
- `reference_type`
- `reference_name`

Instead, Salary Slip linkage is preserved in:
- JE `user_remark`
- JE row `user_remark`

## Payroll frequency limitation
Federal withholding automation in this script is currently implemented for:
- `Weekly`

If payroll frequency changes, the federal withholding logic must be expanded before production use.

---

# Start-of-year update procedure

Before the first payroll of a new calendar year, review and update the payroll script.

## Federal updates
Update:
- `FEDERAL_WEEKLY_TABLES_2026`
- any constants or logic tied to IRS Publication 15-T for the new year
- any supported W-4 logic if the IRS changes the format or calculation rules

## FICA updates
Update:
- `SS_WAGE_BASE_2026`
- if rates ever change:
  - `SS_RATE`
  - `MEDICARE_RATE`

## Colorado updates
Update:
- `COLORADO_RATE_2026`
- Colorado subtraction/default amounts in `calculate_colorado_withholding_2026()`
- any DR 1098 / DR 0004 rule changes

## After annual updates
Run a validation payroll test and confirm:
- gross pay is correct
- employee deductions are correct
- employer taxes are correct
- net pay is correct
- liability summary is correct
- JE preview balances
- draft JE creation still works

---

# Employee pay-rate update procedure

When an employee’s hourly rate changes:

```python
update_employee_tax_profile(
    employee="HR-EMP-00001",
    hourly_rate=22.50,
)
```

Then verify:

```python
get_employee_tax_profile("HR-EMP-00001")
```

Then rerun payroll for a test period and confirm the new gross calculation is correct.

---

# New federal W-4 update procedure

When an employee submits a new federal W-4, map it into the stored Employee tax profile.

Typical mapping:
- filing status → `rootedops_federal_filing_status`
- Step 2 checkbox → `rootedops_federal_step2_checked`
- Step 3 amount → `rootedops_federal_step3_annual_credits`
- Step 4(a) → `rootedops_federal_step4a_other_income`
- Step 4(b) → `rootedops_federal_step4b_deductions`
- Step 4(c) → `rootedops_federal_step4c_extra_withholding`
- exempt status → `rootedops_federal_exempt`

Example:
```python
update_employee_tax_profile(
    employee="HR-EMP-00001",
    federal_profile={
        "filing_status": "Head of Household",
        "step2_checked": 0,
        "step3_annual_credits": 2000.0,
        "step4a_other_income": 0.0,
        "step4b_deductions": 0.0,
        "step4c_extra_withholding": 0.0,
        "exempt": 0,
    },
)
```

Then:
1. inspect `get_employee_tax_profile(employee)`
2. run `rebuild_hourly_salary_slip(...)`
3. confirm the new federal withholding looks correct

---

# New Colorado withholding update procedure

When an employee submits or changes Colorado withholding values:

Default subtraction amount:
```python
update_employee_tax_profile(
    employee="HR-EMP-00001",
    colorado_profile={
        "filing_status": "Single",
        "dr0004_line2": None,
        "dr0004_line3": 0.0,
        "exempt": 0,
    },
)
```

Explicit line 2 override:
```python
update_employee_tax_profile(
    employee="HR-EMP-00001",
    colorado_profile={
        "filing_status": "Single",
        "dr0004_line2": 8000.0,
        "dr0004_line3": 5.0,
        "exempt": 0,
    },
)
```

Then:
1. inspect `get_employee_tax_profile(employee)`
2. run `rebuild_hourly_salary_slip(...)`
3. confirm the new Colorado withholding looks correct

---

# Validation checklist before using a real employee

## Employee / payroll setup
- Employee exists and is active
- Salary Structure Assignment exists and is submitted
- Employee has RootedOps hourly/tax custom fields populated
- Attendance rows for the pay period are submitted and have working hours

## Accounting setup
- `Payroll Expense - DML` exists
- `Payroll Tax Expense - DML` exists
- `Payroll Payable - DML` exists
- `Payroll Tax Payable - DML` exists
- `Payroll Withholding Payable - DML` exists
- company default payroll payable account is set to `Payroll Payable - DML`

## Script validation
- `rebuild_hourly_salary_slip()` returns expected gross, deductions, and net
- `issues == []`
- `diagnostic` rows show `depends_on_payment_days = 0`
- `journal_entry_preview["is_ready_to_create"] == True`

## Journal Entry validation
After preview looks right:
```python
create_payroll_journal_entry_draft(result)
```

Then confirm in ERPNext:
- Accounting → Journal Entry
- draft JE exists
- debits equal credits
- account mapping is correct

---

# Recommended next phase

## Phase 4 — Payroll batching and operationalization
In progress.

Completed in this step:
1. batch multiple salary slips into one payroll-period run
2. create consolidated payroll register output
3. create one consolidated Journal Entry preview for a payroll period
4. create one consolidated draft Journal Entry for a payroll period

Next work:
1. add duplicate-run safeguards for consolidated JE creation
2. add stronger validation and reconciliation helpers
3. decide whether to introduce Payroll Entry objects or continue using the custom scripted path
4. document first real employee onboarding using actual W-4 and Colorado inputs
5. document a payroll operator checklist

---

# Suggested opening request for the next ChatGPT session

"""
Continue RootedOps ERPNext payroll Phase 4. Phase 4 batching basics are now implemented in `erpnext/scripts/50_hourly_payroll_automation.py`, including `run_batched_hourly_payroll()`, consolidated register output, and consolidated Journal Entry preview/draft creation. Review `erpnext/CHATGPT_HANDOFF.md`, `erpnext/CHATGPT_HANDOFF.json`, `erpnext/README.md`, `erpnext/scripts/README_SCRIPTS.md`, and `erpnext/scripts/50_hourly_payroll_automation.py`. Next, harden the payroll-period workflow with reconciliation checks, duplicate-run safeguards, and an operator checklist.
"""

---

# Creating a second payroll test employee

Before testing batched payroll across multiple employees, create the additional employee in a consistent way with `21_create_employee.py`.

Copy the script into the ERPNext container:

```bash
sudo docker cp erpnext/scripts/21_create_employee.py   erpnext-backend:/home/frappe/frappe-bench/sites/21_create_employee.py
```

Load it in bench console:

```python
exec(open("/home/frappe/frappe-bench/sites/21_create_employee.py").read(), globals())
```

Example call for a second test employee:

```python
result = create_or_update_employee(
    employee_name="Payroll Test Employee 2",
    first_name="Payroll",
    last_name="Employee 2",
    user_email="payroll.test2@example.com",
    company="Dank Mushrooms, LLC",
    department="Operations - DML",
    designation="Cultivation Technician",
    default_shift="Day Shift",
    shift_assignment_start_date="2026-03-01",
    hourly_rate=22.50,
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

Notes:
- `user_email` is the safest lookup key. Re-running the helper with the same email updates the same Employee instead of creating another one.
- `employee_name` is the display name, not the ERPNext employee ID.
- The actual employee ID will be returned in `result["employee"]`.
- If the payroll custom fields do not exist in the site yet, the helper skips those fields instead of failing.
- Use the returned employee ID in attendance/checkin setup and later batch payroll tests.


### Recommended payroll-ready employee setup

```python
exec(open("/home/frappe/frappe-bench/sites/21_create_employee.py").read(), globals())

result = create_or_update_employee(
    employee_name="Payroll Test Employee 3",
    first_name="Payroll",
    last_name="Employee 3",
    user_email="payroll.test3@example.com",
    company="Dank Mushrooms, LLC",
    department="Operations - DML",
    designation="Cultivation Technician",
    default_shift="Day Shift",
    shift_assignment_start_date="2026-03-15",
    hourly_rate=22.50,
    salary_structure="Dank Mushrooms Weekly Test",
    salary_structure_assignment_start_date="2026-03-15",
    salary_structure_base=800.0,
    create_salary_structure_assignment=True,
    federal_profile={"filing_status": "Single", "step2_checked": 0, "step3_annual_credits": 0.0, "step4a_other_income": 0.0, "step4b_deductions": 0.0, "step4c_extra_withholding": 0.0, "exempt": 0},
    colorado_profile={"filing_status": "Single", "dr0004_line2": None, "dr0004_line2_override": 0, "dr0004_line3": 0.0, "exempt": 0},
)
result
```

After inserting test checkins, `run_batched_hourly_payroll()` now processes auto attendance first by default before rebuilding salary slips.


# Multi-employee validation status

Validated payroll batches:
- 2-employee batch validated successfully for `2026-03-15` through `2026-03-21`
- 3-employee batch validated successfully for `2026-03-15` through `2026-03-21`

Verified three-employee pay results:
- `HR-EMP-00001` gross `400.00`, net `347.45`
- `HR-EMP-00002` gross `472.50`, net `403.96`
- `HR-EMP-00003` gross `258.75`, net `232.23`

# Hardening now present in `50_hourly_payroll_automation.py`

The payroll script now surfaces these problems earlier:
- employee hourly rate is missing or `<= 0`
- checkins in the pay period exist but attendance resolves to `0.0` hours
- checkins in the pay period have `skip_auto_attendance = 1`
- federal or Colorado filing status is missing when attendance hours exist

These diagnostics are included in payroll results and can stop a run before a zero-hour employee silently reaches the batch.

# Clean fourth-employee validation procedure

## 1. Create employee 4 with payroll-ready onboarding
```python
exec(open("/home/frappe/frappe-bench/sites/21_create_employee.py").read(), globals())

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
    federal_profile={"filing_status": "Single", "step2_checked": 0, "step3_annual_credits": 0.0, "step4a_other_income": 0.0, "step4b_deductions": 0.0, "step4c_extra_withholding": 0.0, "exempt": 0},
    colorado_profile={"filing_status": "Single", "dr0004_line2": None, "dr0004_line2_override": 0, "dr0004_line3": 0.0, "exempt": 0},
)
result
```

## 2. Create clean checkins
```python
insert_checkin_pair("HR-EMP-00004", "2026-03-16 09:00:00", "2026-03-16 13:00:00")
insert_checkin_pair("HR-EMP-00004", "2026-03-17 10:00:00", "2026-03-17 15:30:00")
insert_checkin_pair("HR-EMP-00004", "2026-03-18 08:30:00", "2026-03-18 12:30:00")
```

## 3. Process auto attendance and confirm hours
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
    fields=["attendance_date", "status", "working_hours", "docstatus"],
    order_by="attendance_date asc",
)
```

## 4. Run the four-employee batch
```python
exec(open("/home/frappe/frappe-bench/sites/50_hourly_payroll_automation.py").read(), globals())

batch = run_batched_hourly_payroll(
    employees=["HR-EMP-00001", "HR-EMP-00002", "HR-EMP-00003", "HR-EMP-00004"],
    start_date="2026-03-15",
    end_date="2026-03-21",
    company="Dank Mushrooms, LLC",
)
```

## 5. Confirm all four employees contributed wages
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


# Clean handoff state after four-employee validation

A clean four-employee payroll batch has now been validated with these per-employee results for pay period `2026-03-15` to `2026-03-21`:
- `HR-EMP-00001` → Gross `400.00`, Net `347.45`
- `HR-EMP-00002` → Gross `472.50`, Net `403.96`
- `HR-EMP-00003` → Gross `258.75`, Net `232.23`
- `HR-EMP-00004` → Gross `600.00`, Net `502.31`

The current scripts are strong enough to continue validation, but the next session should stop extending bench-console-only operation and instead design the ERPNext UI / automation-hook layer around the now-working payroll engine.

## Recommended next-session objectives
- decide the UI entry point for weekly payroll runs
- wrap `run_batched_hourly_payroll(...)` behind a server-side method callable from ERPNext UI
- decide where operator review, approval, and accounting links should live in the UI
- add payment and reserve-transfer workflow after payroll accrual review
