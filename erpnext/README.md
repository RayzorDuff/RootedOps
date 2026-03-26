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
