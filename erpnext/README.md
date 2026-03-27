# RootedOps ERPNext Configuration Guide

This directory contains the ERPNext-specific configuration assets for RootedOps.

Primary focus:
- Dank Mushrooms, LLC payroll and accounting
- Rooted Psyche accounting and future payroll
- employee attendance and hourly payroll support
- ERPNext configuration assets that combine CSV imports, bench-console scripts, and the new Payroll Entry UI integration layer

This README is the high-level configuration guide. Script-level operating details now live in `scripts/README_SCRIPTS.md`. The active session handoff lives in `CHATGPT_HANDOFF.md` and `CHATGPT_HANDOFF.json`.

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
- validated a clean four-employee payroll run with nonzero gross/net pay for all four employees and a balanced consolidated JE preview

Result:
- One pay period can now be processed in batch with one Salary Slip per employee and one consolidated accrual JE preview or draft.

## Phase 5 — Payroll Entry UI integration and first hardening pass
In progress, with the first working operator flow completed.

Accomplished:
- extracted the payroll engine into an importable Frappe app module in `rootedops_payroll.services.payroll_engine` in the live environment
- added a thin API layer in `rootedops_payroll.api.payroll_entry_actions`
- confirmed the API can:
  - read a saved `Payroll Entry`
  - discover employees with attendance in the period
  - preview attendance-driven payroll for the period
  - create or refresh draft Salary Slips from the Payroll Entry context
  - create a consolidated draft Journal Entry from the Payroll Entry context
- added a Payroll Entry client-script workflow with three buttons:
  - `Preview Attendance Payroll`
  - `Create / Refresh Draft Salary Slips`
  - `Create Consolidated Draft JE`
- added Payroll Entry custom fields for writeback:
  - `rootedops_consolidated_journal_entry`
  - `rootedops_salary_slip_count`
  - `rootedops_last_processed_on`
  - `rootedops_payroll_summary`
- added writeback so Payroll Entry now stores the JE link, slip count, processing timestamp, and a summary snapshot
- added the first duplicate-JE safeguard so the same Payroll Entry cannot create another consolidated JE once one is already linked

Result:
- normal weekly payroll operation no longer depends on bench console
- the operator can now work from standard ERPNext forms: `Payroll Entry`, `Salary Slip`, and `Journal Entry`

---

# Higher-Level Project State

## What is working now
The core payroll stack is now split into three layers:

1. **Attendance / HR layer**
   - Employee Checkin
   - Shift Assignment
   - Attendance auto-generation

2. **Payroll engine layer**
   - `scripts/50_hourly_payroll_automation.py` remains the source script in this repo
   - the same logic has been extracted into the live `rootedops_payroll.services.payroll_engine` module for UI/server use

3. **ERPNext operator workflow layer**
   - `Payroll Entry` is now the operator launch point
   - draft Salary Slips are reviewed in standard ERPNext
   - the consolidated payroll accrual JE is reviewed in standard ERPNext

## What is still not fully hardened
These are the main items left before treating the flow as "production-routine" rather than "working and validated":

- stronger duplicate Salary Slip protections for the same employee and date range
- clearer operator warnings when submitted Salary Slips already exist for the period
- better popup responses with direct links to slips and the JE
- final documented payment / disbursement workflow using `Payment Entry`, bank ledgers, and reconciliation
- deciding whether the temporary database `Client Script` should later be moved into the app asset pipeline once the Docker/frontend app packaging is cleaned up

## Recommended next phase naming
For future sessions, use this phase breakdown:

- **Phase 5A** — payroll engine extraction into importable app code
- **Phase 5B** — Payroll Entry UI integration through whitelisted methods and client script
- **Phase 5C** — Payroll Entry writeback fields and duplicate consolidated JE protection
- **Phase 5D** — Salary Slip duplicate hardening, better UI responses, and operator polish
- **Phase 6** — payment workflow, bank ledger usage, reconciliation, and reserve-transfer helpers

---

# Latest Verified Working State

## Test employee baseline
- Employee: `HR-EMP-00001`
- Company: `Dank Mushrooms, LLC`
- Hourly rate stored on Employee: `20.00`

## Verified single-employee payroll calculation for period `2026-03-15` to `2026-03-21`
- Hours: `20.0`
- Gross: `400.00`
- Employee Social Security: `24.80`
- Employee Medicare: `5.80`
- Federal withholding: `9.00`
- Colorado withholding: `12.95`
- Employer Social Security: `24.80`
- Employer Medicare: `5.80`
- Net pay: `347.45`

## Verified four-employee payroll batch for period `2026-03-15` to `2026-03-21`
- `HR-EMP-00001` gross/net: `400.00 / 347.45`
- `HR-EMP-00002` gross/net: `472.50 / 403.96`
- `HR-EMP-00003` gross/net: `258.75 / 232.23`
- `HR-EMP-00004` gross/net: `600.00 / 502.31`

## Verified liability summary
- consolidated JE preview remained balanced
- payroll account mapping remained:
  - `Payroll Expense - DML` → gross wages expense
  - `Payroll Tax Expense - DML` → employer payroll tax expense
  - `Payroll Payable - DML` → net payroll payable
  - `Payroll Tax Payable - DML` → Social Security and Medicare payable
  - `Payroll Withholding Payable - DML` → federal and Colorado withholding payable

## Verified UI-integrated operator flow
Using a saved `Payroll Entry` for `2026-03-15` to `2026-03-21`, the following were successfully executed from ERPNext UI:
- `Preview Attendance Payroll`
- `Create / Refresh Draft Salary Slips`
- `Create Consolidated Draft JE`

Confirmed outcomes:
- draft Salary Slips were created / refreshed from the Payroll Entry context
- a consolidated draft Journal Entry was created from the Payroll Entry context
- Payroll Entry writeback fields populated in the form UI

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

# Current recommended operator workflow

1. employee logs IN / OUT through ERPNext
2. auto attendance resolves hours worked
3. operator opens or creates the weekly `Payroll Entry`
4. operator clicks `Preview Attendance Payroll`
5. operator reviews `RootedOps Payroll Summary`
6. operator clicks `Create / Refresh Draft Salary Slips`
7. operator reviews draft `Salary Slip` records
8. operator clicks `Create Consolidated Draft JE`
9. operator reviews and submits the draft `Journal Entry`
10. operator later uses `Payment Entry` against the real bank ledger to disburse wages and remit liabilities

---

# Recommended next work

## Immediate hardening
- block or warn if submitted Salary Slips already exist for the same employee and period
- make Salary Slip duplicate handling more explicit in the API wrapper
- improve popup messages with direct links to the created Salary Slips and Journal Entry

## Accounting / disbursement layer
- document the bank ledger and `Bank Account` setup clearly
- document or script the `Payment Entry` workflow for:
  - net wages
  - payroll taxes
  - withholding remittance

## Packaging / repo hygiene
- include the full `rootedops_payroll` app tree in the next repo export so the UI/server integration changes are versioned in the same place as the ERPNext scripts
- reconcile Docker/frontend app packaging so app JS can eventually live in the app rather than only in a database Client Script


---

# Phase 6 — Hybrid Shift / Multi-Company Payroll Hardening
Completed and documented.

Accomplished:
- added a second payroll business, `Raymond Danks`, alongside `Dank Mushrooms, LLC`
- configured payroll account expectations for a nanny / care-provider reimbursement business
- validated a second payroll model: `hybrid_overnight`
- added Employee-level fields for hybrid shift compensation:
  - `rootedops_pay_model`
  - `rootedops_overnight_flat_amount`
- implemented hybrid shift pay logic for an employee who is paid:
  - normal hourly wages for standard hours
  - a flat overnight amount for a complete `10:00 PM` to `6:00 AM` block
  - normal hourly wages if only part of that overnight window is worked
- confirmed that a same-session overnight block such as `22:00 → 06:00` can be paid as a flat amount when it matches the full overnight rule
- documented the current limitation / future enhancement:
  - **Potential enhancement:** extract overnight sub-blocks from longer sessions (for example `06:00 day 1 → 06:00 day 2`) so the overnight middle segment can be paid flat while the surrounding hours remain hourly
- hardened payroll diagnostics around checkins and attendance
- identified and documented the account-mapping bug where wage expense could be posted to payroll tax expense when keyword guessing was used
- documented the correct long-term accounting fix:
  - derive wage expense lines from the **Salary Component Account** mappings on the Salary Slip
  - keep employer payroll taxes on the payroll tax expense account

Result:
- the payroll engine now supports multi-company payroll patterns and a second compensation model beyond simple hourly labor
- the documentation now supports onboarding a real employee in either business without repeating the earlier trial-and-error setup steps

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
