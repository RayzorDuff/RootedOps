# RootedOps ERPNext Configuration Guide

This directory contains the ERPNext-specific configuration assets for RootedOps.

Primary focus:
- Dank Mushrooms, LLC payroll and accounting
- Raymond Danks nanny / household payroll
- employee attendance and hourly payroll support
- ERPNext configuration assets that combine CSV imports, bench-console scripts, app code, and Payroll Entry UI integration

This README is the high-level guide. Detailed script operation notes live in `scripts/README_SCRIPTS.md`. The active handoff lives in `CHATGPT_HANDOFF.md` and `CHATGPT_HANDOFF.json`.

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
- created and submitted `Shift Assignment` rows
- confirmed clean `Employee Checkin` rows convert into `Attendance`
- confirmed `working_hours` is populated from check-in/check-out data

Result:
- Attendance is now a reliable source of hours worked.

## Phase 2 — Hourly payroll foundation
Completed.

Accomplished:
- switched Payroll Settings from leave-based payroll to attendance-based payroll
- verified the stock ERPNext payment-days model is not a good fit for this ad-hoc hourly employee use case
- created a custom Python payroll automation approach
- confirmed attendance-derived hours can be turned into gross pay plus employee/employer FICA
- confirmed custom draft Salary Slip generation works from a script loaded into bench console

Result:
- The system has a working scripted baseline for hourly payroll.

## Phase 3 — Withholding automation, employee tax profiles, and Journal Entry draft creation
Completed.

Accomplished:
- resolved the original net-pay mismatch caused by ERPNext salary-structure recalculation
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

## Phase 4 — Batch payroll-period runs and consolidated Journal Entry foundation
Completed and validated.

Accomplished:
- added batched payroll-period helpers to `scripts/50_hourly_payroll_automation.py`
- added consolidated payroll register output
- added consolidated liability summary output
- added consolidated Journal Entry preview generation
- added draft consolidated Journal Entry creation support
- preserved the existing single-slip workflow for isolated testing
- updated `scripts/21_create_employee.py` so new payroll-test employees are payroll-ready on creation
- added helpers for backfilling payroll setup on older employees and creating clean IN/OUT checkin pairs
- hardened payroll diagnostics so zero-hour attendance and `skip_auto_attendance = 1` checkins are surfaced immediately
- validated clean multi-employee payroll runs with nonzero gross/net pay and a balanced consolidated JE preview

Result:
- One pay period can now be processed in batch with one Salary Slip per employee and one consolidated accrual JE preview or draft.

## Phase 5 — Payroll Entry UI integration and hardening
Completed for the current operator flow.

Accomplished:
- extracted payroll engine logic into importable app code under `erpnext/apps/rootedops_payroll/rootedops_payroll/services/payroll_engine.py`
- added whitelisted Payroll Entry API methods under `erpnext/apps/rootedops_payroll/rootedops_payroll/api/payroll_entry_actions.py`
- added Payroll Entry client script under `erpnext/client_scripts/payroll_entry_rootedops_payroll.js`
- validated the following buttons in the UI:
  - `Preview Attendance Payroll`
  - `Create / Refresh Draft Salary Slips`
  - `Create Consolidated Draft JE`
- fixed hybrid overnight reporting so overnight sessions count toward displayed hours
- fixed persistence of final `total_working_hours`, `payment_days`, `total_working_days`, and `absent_days` on Salary Slip for the hybrid path
- confirmed the Payroll Entry form may require a browser reload after client script updates before the new buttons appear or behave correctly

Result:
- Payroll Entry is now a working operator-facing entry point for payroll preview, draft Salary Slip generation, and consolidated accrual JE creation.

## Phase 6 — Bank setup, payroll account map audit, and payroll cash flow preview
Completed for preview mode.

Accomplished:
- configured Dank Mushrooms bank defaults to use:
  - checking: `Dank Mushrooms Checking - High Plains Bank`
  - withholding: `Dank Mushrooms Withholding - High Plains Bank`
- created Raymond Danks bank infrastructure:
  - bank: `Elevations Credit Union`
  - checking bank account master and GL link
  - withholding savings bank account master and GL link
  - default bank account set to Raymond Danks checking
- audited both companies for:
  - payroll expense account
  - payroll tax expense account
  - payroll payable
  - payroll tax payable
  - payroll withholding payable
  - default bank account
  - checking and withholding bank GL accounts
- confirmed missing account map keys are empty for both companies
- extended `payroll_engine.py` with payroll cash-flow preview helpers for:
  - employee payment from checking
  - tax reserve transfer from checking to withholding bank
  - payroll tax remittance from withholding bank
- added `preview_payroll_cash_flow` server action in `payroll_entry_actions.py`
- added `Preview Payroll Cash Flow` button to the Payroll Entry client script
- validated the new modal preview in the UI after reloading the website

Result:
- The system can now preview the accounting cash flow that follows payroll accrual, using real configured checking and withholding bank accounts.

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
| `scripts/60_setup_payroll_entry_ui_support.py` | Creates the custom Payroll Entry fields used by the UI integration layer |
| `scripts/README_SCRIPTS.md` | Script usage notes, payroll automation details, maintenance procedures, and validation steps |
| `scripts/70_phase6_bank_setup.py` | if bank accounts are missing or defaults are blank.
| `scripts/71_phase6_payroll_account_audit.py` | to confirm account mapping is complete.

## UI integration reference files
| File | Purpose |
|---|---|
| `client_scripts/payroll_entry_rootedops_payroll.js` | Reference copy of the working Payroll Entry Client Script that was stored in the ERPNext database |
| `apps/rootedops_payroll/rootedops_payroll/api/payroll_entry_actions.py` | Thin API layer used by the Payroll Entry UI buttons |

## Handoff files
| File | Purpose |
|---|---|
| `CHATGPT_HANDOFF.md` | Narrative handoff for a new ChatGPT session |
| `CHATGPT_HANDOFF.json` | Structured handoff summary |

---

# What still uses CSV imports vs. what is now better done by script or UI

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
- payroll-ready employee creation / update
- salary structure cleanup and recreation
- Payroll Entry custom field creation for the UI layer
- attendance-driven payroll engine logic
- employee payroll tax profile storage

## Now better handled from ERPNext UI
- weekly payroll preview from `Payroll Entry`
- draft Salary Slip creation / refresh from `Payroll Entry`
- consolidated draft Journal Entry creation from `Payroll Entry`
- review of slips and the consolidated JE using standard ERPNext forms

---

# Current operator workflow

For a saved Payroll Entry in the ERPNext UI:

1. Open Payroll Entry.
2. Use `Preview Attendance Payroll` to verify consolidated gross / net / taxes.
3. Use `Create / Refresh Draft Salary Slips` to generate or rebuild the Salary Slips.
4. Use `Create Consolidated Draft JE` to create the payroll accrual JE draft.
5. Use `Preview Payroll Cash Flow` to inspect the next downstream accounting steps:
   - employee payment from checking
   - tax reserve transfer to withholding bank
   - later tax remittance from withholding bank

Important note:
- After changing client script or app code, reload the website before assuming the new UI is broken. In this session, the new Payroll Cash Flow Preview worked after reload.

---

# Verified accounting model

## Payroll accrual
Salary Slips do not directly create bank transactions. First create the payroll accrual JE.

Conceptual JE shape:
- Debit payroll expense
- Debit employer payroll tax expense
- Credit payroll payable
- Credit payroll tax payable / payroll withholding payable

## Employee payment
When the employee is actually paid:
- Debit payroll payable
- Credit checking bank GL account

## Tax reserve transfer
When payroll tax cash is moved into the withholding savings account:
- Debit withholding bank GL account
- Credit checking bank GL account

## Tax remittance
When taxes are actually paid to IRS / Colorado:
- Debit payroll tax payable / payroll withholding payable
- Credit withholding bank GL account

This separation is intentional and should be preserved. Salary Slips create liabilities; bank transactions clear those liabilities later.


---

# Employee Onboarding Runbooks (UI-first, bench-supported)

These are the **authoritative** setup steps for creating a new payroll employee.

## Business types currently covered
- `Dank Mushrooms, LLC` — standard hourly payroll
- `Raymond Danks` — hybrid nanny / caregiver payroll with optional overnight flat block
- `Rooted Psyche` — not yet fully payroll-tested, but should follow the same general pattern once accounts and salary components are mapped

## Golden rule before creating employees
Before creating a real employee, confirm these items **for that company**:

1. Company exists and is active.
2. Payroll accounts exist and are mapped.
3. Salary Components exist and have **Salary Component Account** rows for the company.
4. Salary Structure exists and is **Submitted**.
5. Shift Type exists and is configured for auto attendance if you are using checkins.
6. You know whether the employee is:
   - standard hourly (`Dank Mushrooms`)
   - hybrid overnight (`Raymond Danks`)

If any of the above are missing, employee creation will appear to work, but payroll generation will fail later.

---

## A. Create a new hourly employee in ERPNext UI (recommended default path)

### Step 1 — Create the Employee
ERPNext UI:
- **HR > Employee > New**

Populate at minimum:
- Employee Name
- First Name / Last Name
- Company
- Department
- Designation
- Status = `Active`
- Default Shift = `Day Shift` (or your intended shift)

Save the Employee.

### Step 2 — Create a submitted Shift Assignment
ERPNext UI:
- **Shift & Attendance > Shift Assignment > New**

Populate:
- Employee
- Shift Type = `Day Shift` (or another intended shift)
- Start Date

Then **Submit** the Shift Assignment.

Important:
- If the employee has checkins but **no submitted Shift Assignment**, auto attendance will not behave correctly.

### Step 3 — Create a Salary Structure Assignment
ERPNext UI:
- **Payroll > Salary Structure Assignment > New**

Populate:
- Employee
- Salary Structure
- From Date
- Base

Then **Submit** it.

Important:
- If this is missing, payroll engine calls such as `rebuild_hourly_salary_slip(...)` will fail with:
  - `No submitted Salary Structure Assignment found ...`

### Step 4 — Populate payroll/tax custom fields
If your custom Employee fields are exposed in the UI, populate:
- `rootedops_hourly_rate`
- federal withholding fields
- Colorado withholding fields

If they are **not yet visible in the UI**, use either:
- Customize Form / Custom Field visibility work later, or
- the bench helper script in the next section

### Step 5 — Create checkins from the UI
ERPNext UI:
- **Shift & Attendance > Employee Checkin > Add Employee Checkin**

Rules:
- Use explicit `IN` and `OUT`
- make sure the correct Employee is selected
- make sure `skip_auto_attendance = 0`
- if the row shows `Off-Shift`, that means the time does not align to the assigned shift logic

Then process attendance.

### Step 6 — Verify Attendance before payroll
Bench console or reports:
- confirm `Attendance` rows exist
- confirm `working_hours > 0` where expected

Do **not** proceed to payroll if the employee has:
- checkins but no Attendance rows
- Attendance rows with `0.0` hours for days that should have paid time
- `skip_auto_attendance = 1` on the relevant checkins

---

## B. Create a payroll-ready employee from bench (recommended when you need reliability)

This is the **least error-prone** method if you want the employee fully payroll-ready in one pass.

### 1. Copy the helper script into the container
```bash
sudo docker cp erpnext/scripts/21_create_employee.py   erpnext-backend:/home/frappe/frappe-bench/sites/21_create_employee.py
```

### 2. Open bench console
```bash
sudo docker compose --env-file ./.env -f docker/docker-compose.yml exec erpnext-backend   bash -lc "bench --site erp.danks.store console"
```

### 3. Load the helper
```python
exec(open("/home/frappe/frappe-bench/sites/21_create_employee.py").read(), globals())
```

### 4. Example — Dank Mushrooms hourly employee
```python
result = create_or_update_employee(
    employee_name="Example Dank Employee",
    first_name="Example",
    last_name="Employee",
    user_email="example.dank@example.com",
    company="Dank Mushrooms, LLC",
    department="Operations - DML",
    designation="Cultivation Technician",
    default_shift="Day Shift",
    shift_assignment_start_date="2026-03-29",
    hourly_rate=22.50,
    salary_structure="Dank Mushrooms Weekly Test",
    salary_structure_assignment_start_date="2026-03-29",
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

### 5. Example — Raymond Danks nanny / caregiver employee
Use the same helper for the base employee creation, then set the hybrid fields after creation.

```python
result = create_or_update_employee(
    employee_name="Example Nanny",
    first_name="Example",
    last_name="Nanny",
    user_email="example.nanny@example.com",
    company="Raymond Danks",
    department="Childcare - RD",
    designation="Nanny",
    default_shift="Day Shift",
    shift_assignment_start_date="2026-03-29",
    hourly_rate=27.00,
    salary_structure="Raymond Danks Hybrid Shift Payroll",
    salary_structure_assignment_start_date="2026-03-29",
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

Then set the hybrid fields:

```python
emp = frappe.get_doc("Employee", result["employee"])
emp.rootedops_pay_model = "hybrid_overnight"
emp.rootedops_overnight_flat_amount = 100.0
emp.save(ignore_permissions=True)
frappe.db.commit()
```

If the fields do not persist through the normal doc save, fallback:

```python
frappe.db.set_value("Employee", result["employee"], "rootedops_pay_model", "hybrid_overnight", update_modified=False)
frappe.db.set_value("Employee", result["employee"], "rootedops_overnight_flat_amount", 100.0, update_modified=False)
frappe.db.commit()
```

---

## C. Clean checkin creation for testing
Use this helper from `21_create_employee.py`:

```python
insert_checkin_pair("HR-EMP-00006", "2026-03-29 09:00:00", "2026-03-29 17:00:00")
```

For hybrid overnight tests:

```python
insert_checkin_pair("HR-EMP-00006", "2026-03-29 22:00:00", "2026-03-30 06:00:00")
insert_checkin_pair("HR-EMP-00006", "2026-03-30 13:00:00", "2026-03-30 17:00:00")
```

Then process attendance:

```python
shift = frappe.get_doc("Shift Type", "Day Shift")
shift.process_auto_attendance()
frappe.db.commit()
```

Then verify:

```python
frappe.get_all(
    "Attendance",
    filters={
        "employee": "HR-EMP-00006",
        "attendance_date": ["between", ["2026-03-29", "2026-04-04"]],
    },
    fields=["name", "attendance_date", "status", "working_hours", "docstatus"],
    order_by="attendance_date asc",
)
```

---

## D. Known employee-creation failure modes

### 1. Employee has checkins but payroll says attendance resolved to 0.0 hours
Usually caused by one of:
- `skip_auto_attendance = 1`
- no submitted Shift Assignment
- stale / bad Attendance rows that need to be canceled and regenerated
- overnight / off-shift logic that did not match the assigned shift

### 2. Employee shows checkins in the UI but bench query returns nothing
Usually caused by one of:
- wrong site / stale console session
- cache / session mismatch
- not querying the right employee or date range

### 3. Salary slip rebuild fails because no Salary Structure Assignment exists
Fix by creating and **submitting** a Salary Structure Assignment.

### 4. Hybrid pay fields save to DB but do not persist via normal doc save
This happened during testing. Current safe fallback is:
- `frappe.db.set_value(...)`

Longer-term improvement:
- ensure the Employee custom fields are correctly surfaced and not being overwritten by another customization layer.

# Company-specific verified configuration

## Dank Mushrooms, LLC
Verified defaults:
- default bank account: `Dank Mushrooms Checking - High Plains Bank`
- default payroll payable: `Payroll Payable - DML`
- checking GL account: `Dank Mushrooms Checking - DML`
- withholding GL account: `Dank Mushrooms Withholding - DML`

Resolved payroll account map:
- payroll expense: `Payroll Expense - DML`
- payroll tax expense: `Payroll Tax Expense - DML`
- payroll payable: `Payroll Payable - DML`
- payroll tax payable: `Payroll Tax Payable - DML`
- payroll withholding payable: `Payroll Withholding Payable - DML`

## Raymond Danks
Verified defaults:
- default bank account: `Raymond Danks Elevations Checking - Elevations Credit Union`
- default payroll payable: `Payroll Payable - RD`
- checking GL account: `Elevations Checking - RD`
- withholding GL account: `Elevations Withholding Savings - RD`

Resolved payroll account map:
- payroll expense: `Nanny Wages - RD`
- payroll tax expense: `Payroll Tax Expense - RD`
- payroll payable: `Payroll Payable - RD`
- payroll tax payable: `Payroll Tax Payable - RD`
- payroll withholding payable: `Payroll Withholding Payable - RD`

---

# Files most relevant to the current workflow

## App code
- `erpnext/apps/rootedops_payroll/rootedops_payroll/services/payroll_engine.py`
- `erpnext/apps/rootedops_payroll/rootedops_payroll/api/payroll_entry_actions.py`

## UI
- `erpnext/client_scripts/payroll_entry_rootedops_payroll.js`

## Setup and validation scripts
- `erpnext/scripts/50_hourly_payroll_automation.py`
- `erpnext/scripts/60_setup_payroll_entry_ui_support.py`
- `erpnext/scripts/70_phase6_bank_setup.py`
- `erpnext/scripts/71_phase6_payroll_account_audit.py`

---

# Next recommended work

The next step should be two more server actions, not just one preview:
- `create_employee_payment_draft_journal_entry`
- `create_tax_reserve_transfer_draft_journal_entry`

That will let the UI move from preview to actual downstream cash-flow draft documents in the same pattern already used for the consolidated payroll accrual JE.
