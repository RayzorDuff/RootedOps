# RootedOps ERPNext Scripts

These scripts are intended to be loaded into `bench --site erp.danks.store console` unless otherwise noted.

This README documents:
- how to load and run the scripts
- what each script currently does
- the verified payroll automation workflow
- the Payroll Entry UI integration support files
- the Phase 6 bank setup and account-audit scripts
- annual and employee-change maintenance procedures
- validation steps before using the process for a real employee

---

# General bench-console pattern

Copy the script into the ERPNext container:

```bash
sudo docker cp erpnext/scripts/<scriptname>.py   erpnext-backend:/home/frappe/frappe-bench/sites/<scriptname>.py
```

Open bench console:

```bash
sudo docker compose --env-file ./.env -f docker/docker-compose.yml exec erpnext-backend   bash -lc "bench --site erp.danks.store console"
```

Load the file:

```python
exec(open("/home/frappe/frappe-bench/sites/<scriptname>.py").read(), globals())
```

This remains the preferred pattern for larger setup / validation scripts because pasting long Python blocks directly into bench console proved unreliable.

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
- hybrid overnight pay model support
- draft Salary Slip rebuilding
- payroll liability summary
- payroll register row output
- Journal Entry preview generation
- draft Journal Entry creation
- batched payroll-period runs
- consolidated payroll register output
- consolidated Journal Entry preview and draft creation

## `60_setup_payroll_entry_ui_support.py`
Creates the custom Payroll Entry fields used by the current UI integration:
- `rootedops_consolidated_journal_entry`
- `rootedops_salary_slip_count`
- `rootedops_last_processed_on`
- `rootedops_payroll_summary`

Use this when rebuilding the Payroll Entry UI workflow in a fresh site.

## `70_phase6_bank_setup.py`
Verifies and creates the company bank setup needed for payroll cash flow.

Current verified result:
- Dank Mushrooms existing High Plains bank setup is reused
- Raymond Danks Elevations checking and withholding bank setup is created if missing
- company default bank account is set correctly

Important implementation notes learned in this session:
- avoid double-appending company abbreviations when creating GL accounts
- on this site, `Bank Account` autoname requires `account_name`
- when creating bank account masters, a partial create may leave bank and GL account records but not the bank account master if payload fields are wrong

## `71_phase6_payroll_account_audit.py`
Read-only audit script that verifies for each company:
- default bank account
- default payroll payable account
- checking bank GL account
- withholding bank GL account
- likely payroll expense account
- likely payroll tax expense account
- likely payroll payable account
- likely payroll tax payable account
- likely withholding payable account
- resolved `rootedops_payroll` account map
- missing account map keys

Use this before relying on Payroll Cash Flow Preview.

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

# Current ERPNext UI usage

Once the Payroll Entry custom fields and Client Script are in place, the normal operator flow is:

1. open or create the weekly `Payroll Entry`
2. click `Preview Attendance Payroll`
3. review the writeback fields on Payroll Entry
4. click `Create / Refresh Draft Salary Slips`
5. review the draft Salary Slips in standard ERPNext
6. click `Create Consolidated Draft JE`
7. review and submit the JE in standard ERPNext

---

# Newer operational notes

## `21_create_employee.py` current role
This script is now the preferred **bench-assisted onboarding helper** for payroll employees.

It should be used whenever you want to avoid missing one of the required setup steps:
- Employee
- Shift Assignment
- Salary Structure Assignment
- hourly rate
- tax profile fields

### Current limitation for hybrid employees
The helper does **not yet fully own** hybrid overnight field persistence in every environment. For hybrid employees, create the employee with the helper, then explicitly verify or set:
- `rootedops_pay_model`
- `rootedops_overnight_flat_amount`

## `50_hourly_payroll_automation.py` and the extracted app engine
The repo script remains the readable source of truth for the payroll logic, but the live ERPNext UI path now depends on the extracted app module:
- `rootedops_payroll.services.payroll_engine`

When debugging UI behavior, always remember:
- editing only the repo script is **not enough**
- the app code inside the container / bench app must also be updated and reloaded

## Account mapping learning
A major payroll-accounting bug was identified:
- wage expense was previously guessed by keyword
- in the Raymond Danks company this caused wages to post to `Payroll Tax Expense - RD`

The correct long-term approach is:
- derive earnings expense accounts from the **Salary Component Account** mappings on the Salary Slip
- keep employer payroll taxes on the payroll tax expense account

This should remain the design standard for future payroll hardening.

---

# Verified end-to-end operator workflow

## Initial or rebuild setup
1. Run the Phase 0 import files if rebuilding from scratch.
2. Run the attendance / shift setup scripts.
3. Run the payroll foundation scripts.
4. Run `60_setup_payroll_entry_ui_support.py` if the Payroll Entry custom fields are missing.
5. Ensure the rootedops payroll app code and client script are updated.
6. Reload the website after client-script updates.
7. Run `70_phase6_bank_setup.py` if bank accounts are missing or defaults are blank.
8. Run `71_phase6_payroll_account_audit.py` to confirm account mapping is complete.

## Payroll Entry UI workflow
For a saved Payroll Entry:
1. `Preview Attendance Payroll`
2. `Create / Refresh Draft Salary Slips`
3. `Create Consolidated Draft JE`
4. `Preview Payroll Cash Flow`

What the cash-flow preview shows:
- checking bank used for employee payment
- withholding bank used for tax reserve transfer and remittance
- net pay to employees
- total tax reserve transfer
- employee taxes
- employer taxes
- whether each downstream JE preview is balanced

---

# Known operational notes

## Browser reload after UI changes
After updating client script or app JS / Python, reload the website before assuming the form is broken. In this session the Payroll Cash Flow Preview button worked after reload.

## Hybrid overnight payroll
The hybrid overnight path required fixes so that:
- overnight sessions count toward displayed total working hours
- final summary fields persist to Salary Slip after rebuild

## Salary Slip field note
`total_working_hours` exists in DocType metadata on this site. Earlier attempts to create it as a new Custom Field failed because it already existed.

---

# Current next step

The next implementation target is not more previewing. It is adding two more server actions so Payroll Entry can create downstream cash-flow drafts directly:
- `create_employee_payment_draft_journal_entry`
- `create_tax_reserve_transfer_draft_journal_entry`

