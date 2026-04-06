# RootedOps ERPNext Configuration Guide

This directory contains the ERPNext-specific configuration, bootstrap assets, payroll automation code, and operator workflow references for the RootedOps stack.

Primary focus:
- **Dank Mushrooms, LLC** payroll and accounting
- **Raymond Danks** household / nanny payroll
- **Rooted Psyche** accounting now, with payroll intended later
- attendance-driven hourly payroll in ERPNext / HRMS
- a repo structure that can both:
  - rebuild this environment on a fresh ERPNext install later, and
  - act as a loosely-followable reference for similar small-business / nonprofit / household payroll setups

This file is the **project-level guide**.

Use the companion files as follows:
- `README_SCRIPTS.md` — script, app-module, client-script, and operator workflow details
- `CHATGPT_HANDOFF.md` — narrative status handoff
- `CHATGPT_HANDOFF.json` — structured status handoff

---

# Guiding documentation split

## `README.md` is for
- project scope
- directory purpose
- environment assumptions
- rebuild strategy
- what is managed by CSV vs scripts vs app code vs ERPNext database state
- phase history and current phase status
- high-level operator workflow
- future implementation direction

## `README_SCRIPTS.md` is for
- exact script purposes
- app-module and client-script responsibilities
- execution patterns
- function-level usage
- troubleshooting
- validation checklists
- maintenance procedures

This split is intentional. The payroll workflow is no longer only a bench-console script exercise; it now spans:
- bootstrap CSVs
- helper scripts
- installed Frappe app code
- ERPNext database-stored Client Script state
- live company / account / bank configuration in the ERPNext database

---

# Current state assumptions

The following are assumed to be true for this repo snapshot:

1. `erpnext/apps/rootedops_payroll` reflects the **current installed custom payroll app code**.
2. `erpnext/client_scripts/payroll_entry_rootedops_payroll.js` reflects the **current live Payroll Entry Client Script** stored in ERPNext.
3. Some **database state will naturally drift** from the repo over time, especially:
   - companies already created
   - chart of accounts already imported and adjusted
   - bank accounts and default-bank settings
   - Salary Components and Salary Component Account rows
   - Company payroll-account settings
   - Custom Field / Client Script records stored in the ERPNext database
4. That database drift is expected and does **not** mean the repo is wrong. It means this repo should be read as a:
   - reproducible configuration baseline, and
   - documented operating model.

For a true clean-room rebuild in the future, expect to use **both** this repo **and** the documented ERPNext UI / importer / patch steps.

---

# Directory map

## Bootstrap CSV files
These remain useful for fresh installs and for documenting baseline master-data expectations.

| File | Purpose |
|---|---|
| `companies.csv` | Initial company import for the project companies |
| `chart_of_accounts_dank_mushrooms_llc.csv` | Dank Mushrooms chart of accounts baseline |
| `chart_of_accounts_rooted_psyche.csv` | Rooted Psyche chart of accounts baseline |
| `cost_centers.csv` | Cost center import |
| `departments.csv` | Department import |
| `designations.csv` | Designation import |
| `employees_template.csv` | Employee import template |
| `bank_accounts_template.csv` | Example / template bank-account import structure |
| `suppliers.csv` | Supplier import |
| `projects.csv` | Project import |
| `expense_claim_types.csv` | Expense claim type import |
| `asset_categories.csv` | Asset category import |

## Bench/helper scripts
These scripts help create or validate ERPNext state that proved cumbersome or error-prone through the UI alone.

| File | Purpose |
|---|---|
| `scripts/10_setup_master_data.py` | Creates or repairs cost centers, departments, designations, and supporting master data |
| `scripts/20_setup_shift_and_test_employee.py` | Creates or repairs Day Shift, Payroll Settings, test employee, and Shift Assignment |
| `scripts/21_create_employee.py` | Creates or updates a payroll-ready employee, User, payroll custom fields, and Shift Assignment |
| `scripts/30_create_employee_home_page.py` | Creates the file-backed custom employee landing page |
| `scripts/40_setup_payroll_test_foundation.py` | Creates or repairs the test salary structure / assignment baseline |
| `scripts/50_hourly_payroll_automation.py` | Bench-friendly reference implementation of the payroll engine and helper workflows |
| `scripts/60_setup_payroll_entry_ui_support.py` | Creates the Payroll Entry custom fields used by the UI integration layer |
| `scripts/61_add_salary_slip_hours_field.py` | Adds / repairs Salary Slip fields needed for final hours display or writeback |
| `scripts/70_phase6_bank_setup.py` | Creates or repairs bank-account and default-bank setup used in payroll cash-flow steps |
| `scripts/71_phase6_payroll_account_audit.py` | Audits payroll account mapping and bank-account linkage |

## Installed app code
This is the actual custom Frappe app layer used by the UI workflow.

| File / path | Purpose |
|---|---|
| `apps/rootedops_payroll/rootedops_payroll/services/payroll_engine.py` | Main reusable payroll engine logic |
| `apps/rootedops_payroll/rootedops_payroll/api/payroll_entry_actions.py` | Whitelisted Payroll Entry actions exposed to the ERPNext UI |
| `apps/rootedops_payroll/rootedops_payroll/hooks.py` | App hooks / client-side inclusion and app wiring |
| `apps/rootedops_payroll/rootedops_payroll/public/js/payroll_entry.js` | App-side JS reference for Payroll Entry UI behavior |

## ERPNext database-backed UI reference
| File | Purpose |
|---|---|
| `client_scripts/payroll_entry_rootedops_payroll.js` | Reference copy of the working Payroll Entry Client Script stored in the ERPNext database |

## Handoff files
| File | Purpose |
|---|---|
| `CHATGPT_HANDOFF.md` | Narrative handoff for the next working session |
| `CHATGPT_HANDOFF.json` | Structured handoff for the next working session |

---

# What belongs where in a rebuild

## Best handled by CSV import
These are relatively stable and should remain simple import artifacts unless there is a strong reason to fully script them:
- companies
- chart of accounts
- suppliers
- projects
- asset categories
- expense claim types
- some bank-account seed data if desired

## Best handled by helper script
These proved fragile, repetitive, or too easy to misconfigure manually:
- payroll settings
- shift setup
- shift assignment creation for testing
- payroll-ready employee creation / update
- salary structure cleanup and recreation
- Payroll Entry custom field support
- bank setup audit / helper creation

## Best handled by installed app code
These now belong in reusable app code rather than one-off bench work:
- payroll engine logic
- Payroll Entry server actions
- consolidated preview / draft creation helpers
- payroll cash-flow preview builders
- downstream payroll document creation logic as Phase 6 continues

## Best handled in ERPNext UI / database state
These remain operator-facing and should exist in normal ERPNext records:
- Payroll Entry documents
- Salary Slips
- Journal Entries
- Salary Components and Salary Component Account rows
- company account defaults
- bank account masters and default-bank assignments
- Client Script records in ERPNext

---

# Phase history

## Phase 0 — Initial ERPNext configuration pack
Completed.

Scope:
- companies
- chart of accounts CSVs
- cost centers
- departments
- designations
- suppliers
- projects
- bank-account template
- asset categories
- expense claim types
- employee template

Result:
- a reusable bootstrap pack exists for a fresh ERPNext installation.

## Phase 1 — Attendance foundation
Completed.

Accomplished:
- Day Shift created and validated
- auto attendance enabled
- check-in interpretation standardized to explicit log type
- submitted Shift Assignment rows created
- clean Employee Checkin rows verified to produce Attendance
- Attendance `working_hours` verified

Result:
- Attendance is a reliable payroll-hours source.

## Phase 2 — Hourly payroll foundation
Completed.

Accomplished:
- Payroll Settings moved from leave-based to attendance-based logic
- stock ERPNext payment-days proration was tested and rejected for this use case
- custom attendance-driven hourly payroll logic implemented
- attendance-derived hours successfully converted into gross pay and employee/employer FICA
- draft Salary Slip creation from custom logic validated

Result:
- a working scripted hourly-payroll foundation exists.

## Phase 3 — Withholding automation, employee tax profiles, and Journal Entry draft creation
Completed.

Accomplished:
- net-pay mismatch traced to ERPNext salary-structure recalculation and resolved
- federal withholding for 2026 weekly payroll added
- Colorado withholding for 2026 added
- employee tax-profile custom fields persisted on Employee
- employee hourly-rate custom field persisted on Employee
- payroll liability summary added
- payroll register output added
- Journal Entry preview added
- draft Journal Entry creation added

Result:
- a full single-employee payroll calculation works end-to-end through draft Salary Slip and draft accrual JE creation.

## Phase 4 — Batched payroll-period runs and consolidated accrual Journal Entry support
Completed and validated.

Accomplished:
- batched payroll-period helpers added
- consolidated payroll register output added
- consolidated liability summary output added
- consolidated Journal Entry preview generation added
- consolidated draft Journal Entry creation added
- one-slip debugging path preserved
- payroll diagnostics hardened for zero-hour attendance and skipped auto attendance
- multi-employee runs validated with balanced consolidated JE preview

Result:
- one pay period can be processed in batch with one slip per employee and one consolidated accrual JE draft / preview.

## Phase 5 — Payroll Entry UI integration and hardening
Completed for the current operator flow.

Accomplished:
- payroll engine extracted into `rootedops_payroll.services.payroll_engine`
- whitelisted Payroll Entry actions added in `rootedops_payroll.api.payroll_entry_actions`
- Payroll Entry Client Script created and mirrored in this repo
- UI buttons verified:
  - `Preview Attendance Payroll`
  - `Create / Refresh Draft Salary Slips`
  - `Create Consolidated Draft JE`
- hybrid overnight handling hardened so displayed hours and final Salary Slip totals persist correctly

Result:
- Payroll Entry is the operator-facing entry point for preview, draft slip creation, and consolidated accrual JE creation.

## Phase 6 — Bank setup, payroll account audit, and payroll cash-flow preview
Completed for preview mode.

Accomplished:
- Dank Mushrooms bank defaults verified / corrected
- Raymond Danks checking and withholding bank structure created
- both companies audited for payroll expense, payroll tax expense, payroll payable, payroll tax payable, withholding payable, and bank mappings
- account-map gaps confirmed resolved for the currently tested companies
- payroll engine extended with payroll cash-flow preview helpers
- Payroll Entry action added for cash-flow preview
- `Preview Payroll Cash Flow` button added and verified in the UI

Result:
- the system can preview the accounting cash flow that follows payroll accrual using actual configured checking and withholding bank accounts.

---

# Current status

## What is complete now
The current operator workflow supports:
1. previewing attendance-driven payroll from Payroll Entry
2. creating or refreshing draft Salary Slips
3. creating a consolidated payroll accrual Journal Entry draft
4. previewing the downstream payroll cash flow

## What is not complete yet
Phase 6 is **not fully complete operationally**. The current status is:
- **preview is complete**
- **draft downstream cash-flow document creation is next**

Per the current handoff, the next two intended server actions are:
- `create_employee_payment_draft_journal_entry`
- `create_tax_reserve_transfer_draft_journal_entry`

A later follow-on may also add tax remittance document helpers if that still proves valuable.

---

# Current operator workflow

For a saved Payroll Entry:
1. `Preview Attendance Payroll`
2. review payroll summary and writeback fields
3. `Create / Refresh Draft Salary Slips`
4. review draft Salary Slips in ERPNext
5. `Create Consolidated Draft JE`
6. review the accrual JE in ERPNext
7. `Preview Payroll Cash Flow`
8. review the intended downstream checking / withholding / remittance movement

Important:
- Salary Slips and the consolidated accrual JE create **liabilities and expense recognition**.
- Actual bank movement should be created later through separate downstream accounting entries.
- Do not collapse accrual and cash movement into one accounting step.

---

# Rebuild strategy for a fresh ERPNext installation

A future rebuild should be treated as a layered process.

## Layer 1 — baseline ERPNext / HRMS install
- install ERPNext, HRMS, and supporting apps
- confirm site creation and normal login

## Layer 2 — CSV bootstrap
- import companies
- import chart of accounts
- import departments, designations, cost centers, suppliers, projects, expense claim types, and asset categories

## Layer 3 — helper-script baseline
- run master-data helpers as needed
- create / confirm shifts and Payroll Settings
- create / confirm salary structures and assignments
- create / confirm employee custom fields and Payroll Entry helper fields

## Layer 4 — app-code installation
- install `rootedops_payroll`
- verify hooks and whitelisted methods load correctly
- verify app code and repo code match the intended deployment snapshot

## Layer 5 — ERPNext database configuration
- create Salary Components and Salary Component Account rows for each company
- set company payroll default accounts
- configure bank accounts and default bank account
- create or update the Payroll Entry Client Script in the ERPNext database

## Layer 6 — validation
- create test employees
- generate checkins and Attendance
- run Payroll Entry preview
- create draft slips
- create consolidated draft accrual JE
- preview cash flow

A future fresh install for a different organization should follow the same general sequence even if names, accounts, and salary structures differ.

---

# Company coverage status

## Fully or substantially exercised
- **Dank Mushrooms, LLC**
- **Raymond Danks**

## Partially prepared, not yet payroll-validated to the same depth
- **Rooted Psyche**

Rooted Psyche should follow the same general model, but additional company-specific salary components, account mapping, bank setup, and end-to-end payroll testing are still expected before treating it as production-ready.

---

# Important operational notes

- Reload the website after changing client script or app code before assuming Payroll Entry UI behavior is broken.
- The repo may be structurally current while the ERPNext database remains more evolved in live use. That is expected.
- Salary Component Account rows and bank-account mappings are part of the real operating configuration even though they are not fully represented by CSV alone.
- The repo should be maintained as the **best available reproducible baseline**, not as a claim that every live database row is mirrored here at all times.

---

# Recommended immediate next work

Proceed with **Phase 6B**:
- create employee-payment draft Journal Entry creation from the Payroll Entry UI
- create tax-reserve-transfer draft Journal Entry creation from the Payroll Entry UI
- keep accrual creation and cash movement creation as separate operator steps
- document the resulting accounting flow clearly once those actions exist

After that, consider:
- tax remittance draft creation helpers
- Rooted Psyche company-specific payroll validation
- additional rebuild automation for a more fully repeatable clean install

---

# See also

- `README_SCRIPTS.md`
- `CHATGPT_HANDOFF.md`
- `CHATGPT_HANDOFF.json`
