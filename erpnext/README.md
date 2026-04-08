# RootedOps ERPNext Configuration Guide

This directory contains the ERPNext-specific configuration, bootstrap assets, custom payroll app code, client-script references, Docker/bootstrap notes, and handoff material for the RootedOps stack.

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
- `README_SCRIPTS.md` — script, app-module, client-script, Docker, validation, and troubleshooting details
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
- Docker / app-install persistence notes
- troubleshooting
- validation checklists
- maintenance procedures

This split is intentional. The payroll workflow is no longer only a bench-console script exercise; it now spans:
- bootstrap CSVs
- helper scripts
- installed Frappe app code
- ERPNext database-stored Client Script state
- Docker image / bootstrap configuration
- live company / account / bank configuration in the ERPNext database

---

# Current state assumptions

The following are assumed to be true for this repo snapshot:

1. `erpnext/apps/rootedops_payroll` reflects the **current installed custom payroll app code**.
2. `erpnext/client_scripts/payroll_entry_rootedops_payroll.js` reflects the **current live Payroll Entry Client Script** stored in ERPNext.
3. `docker/erpnext-custom.Dockerfile`, `docker/docker-compose.yml`, and `docker/erpnext-bootstrap.sh` now matter to the payroll workflow because the custom app must persist across clean container recreation.
4. Some **database state will naturally drift** from the repo over time, especially:
   - companies already created
   - chart of accounts already imported and adjusted
   - bank accounts and default-bank settings
   - Salary Components and Salary Component Account rows
   - Company payroll-account settings
   - Custom Field / Client Script records stored in the ERPNext database
   - Holiday Lists / Holiday List Assignments
5. That database drift is expected and does **not** mean the repo is wrong. It means this repo should be read as a:
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
| `scripts/50_hourly_payroll_automation.py` | Bench-friendly reference implementation / mirror of the payroll engine and helper workflows |
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

## Docker / bootstrap
| File | Purpose |
|---|---|
| `../docker/docker-compose.yml` | ERPNext container orchestration; now includes custom app persistence concerns |
| `../docker/erpnext-custom.Dockerfile` | Custom ERPNext image build that must include `rootedops_payroll` |
| `../docker/erpnext-bootstrap.sh` | Site bootstrap / install logic |

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
- downstream payroll document creation logic
- salary-slip submit hardening / post-submit repair logic

## Best handled in ERPNext UI / database state
These remain operator-facing and should exist in normal ERPNext records:
- Payroll Entry documents
- Salary Slips
- Journal Entries
- Salary Components and Salary Component Account rows
- company account defaults
- bank account masters and default-bank assignments
- Holiday Lists and Holiday List Assignments
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
- one pay period can be processed in batch with one slip per employee and one consolidated accrual JE.

## Phase 5 — Payroll Entry UI integration and hybrid-overnight hardening
Completed.

Accomplished:
- payroll engine logic moved into installed app code
- whitelisted Payroll Entry server actions added
- Payroll Entry Client Script created and mirrored into repo
- hybrid overnight pay model implemented
- overnight shifts spanning midnight were split into hourly + overnight-flat segments
- payroll-period boundary handling was corrected so hours after the payroll end date do not leak into the prior run and are captured by the next run
- draft Salary Slip rebuild path hardened for hybrid overnight calculations

Result:
- Payroll Entry became the normal operator surface for previews, draft Salary Slips, and draft payroll accrual JEs.

## Phase 6 — Cash-flow workflow, live payroll execution, submit hardening, and container persistence
Largely completed; a few cleanup items remain.

### Phase 6A — Bank setup, account audit, and cash-flow preview
Completed.

Accomplished:
- Dank Mushrooms bank defaults verified and corrected
- Raymond Danks checking and withholding bank structure created
- payroll expense / tax expense / payable / withholding payable / checking / withholding bank mapping audited for both companies
- payroll engine extended with cash-flow preview builders
- Payroll Entry API extended with `preview_payroll_cash_flow(...)`
- Payroll Entry UI extended with `Preview Payroll Cash Flow`

### Phase 6B — Downstream draft JE actions
Completed.

Accomplished:
- `create_employee_payment_draft_journal_entry(...)`
- `create_tax_reserve_transfer_draft_journal_entry(...)`
- Payroll Entry custom link fields added / repaired for downstream JE references
- preview-schema mismatch fixed so cash-flow preview / draft creation shares normalized payload keys

### Phase 6C — First live payroll cycles and submit hardening
Completed for first live operator workflow; keep validating as more live payrolls are run.

Accomplished:
- first live Raymond Danks payroll cycle executed and validated end-to-end
- first live Dank Mushrooms payroll cycle executed and validated through Salary Slip and draft-JE workflow
- Holiday List / Holiday List Assignment requirements for HRMS submit were discovered and documented
- custom Payroll Entry UI action `Submit Draft Salary Slips` added
- standard Salary Slip form submit is no longer the intended path for custom payroll runs
- `submit_custom_salary_slip(...)` now snapshots row amounts / summary fields, submits, restores controlled fields, and then finalizes
- `repair_salary_slip_totals(...)` now repairs:
  - gross / net / deduction headers
  - YTD / MTD Salary Slip header fields
  - `total_in_words`
  - row-level `Salary Detail.year_to_date`
- print/PDF drift traced to stale `Salary Detail.year_to_date` and stale `total_in_words`, then corrected
- `ytd_gross_before_period(...)` was corrected to use **submitted slips only** (`docstatus = 1`) so draft/test slips do not poison YTD tax logic

### Phase 6D — Docker / app-install persistence
Completed enough for normal use, but still worth monitoring.

Accomplished:
- `rootedops_payroll` persistence across clean container recreation was fixed by updating Docker build / bootstrap flow
- app is now present in `bench list-apps` after clean rebuild
- `payments` was removed from filesystem and `sites/apps.txt`
- verified live loaded source for:
  - `submit_draft_salary_slips(...)`
  - `submit_custom_salary_slip(...)`
  - `repair_salary_slip_totals(...)`

Known follow-up:
- restart/bootstrap logs still showed `erpnext-apps-init` shell syntax error and `erpnext-configurator` `mkdir: missing operand` during one restart cycle; runtime recovered, but Docker bootstrap flow should still be kept under observation.

Result:
- UI-driven payroll is now the primary intended operator workflow.
- Salary Slip submit and PDF values are no longer expected to require bench intervention once the patched app code is loaded.
- Docker rebuild / restart no longer requires reinstalling `rootedops_payroll` by hand when the Docker files in this repo are used.

---

# Current verified operator workflow

For a saved Payroll Entry:
1. `Preview Attendance Payroll`
2. `Create / Refresh Draft Salary Slips`
3. Open / inspect draft Salary Slips if desired
4. `Submit Draft Salary Slips` (**RootedOps button**, not native Salary Slip submit)
5. `Create Consolidated Draft JE`
6. `Preview Payroll Cash Flow`
7. `Create Employee Payment Draft JE`
8. `Create Tax Reserve Transfer Draft JE`
9. review and submit accounting documents in ERPNext only after confirming Salary Slip values and PDF output

Important:
- the native Salary Slip submit action is **not** the intended operator path for these custom payroll slips.
- the RootedOps Payroll Entry submit action should be used so the post-submit repair/finalization path runs.

---

# Current company status summary

## Raymond Danks
Validated through first live payroll cycle.

Key points:
- hybrid overnight payroll path validated
- payroll boundary logic validated across overnight runs
- first live Salary Slip and downstream JEs validated
- Holiday List Assignment requirement discovered during first live run and documented

## Dank Mushrooms, LLC
Validated through first live Salary Slip / submit-hardening cycle and downstream draft-JE path.

Key points:
- low-wage weekly run can legitimately produce `Federal Withholding = 0.00`
- submit path had stale YTD / print-format issues that are now handled in app code
- first real submitted slip for `HR-EMP-00005` is the reference case for verifying row-level YTD and `total_in_words` repairs

## Rooted Psyche
Accounting/configuration only for now.
Payroll is intended later, after the current operator workflow is considered stable.

---

# Known pitfalls

1. **Holiday List Assignment is required for HRMS Salary Slip submit** on this install.
   - Employee holiday_list alone was not sufficient.
   - Use Holiday List Assignment records that are active for the employee/date range.

2. **Do not use the native Salary Slip submit button** for this custom workflow.
   - Use the RootedOps Payroll Entry submit action.

3. **Draft/test slips must not count toward YTD.**
   - `ytd_gross_before_period(...)` was corrected for this.

4. **PDF / print output can expose stale stored fields** even when header totals look correct in the form.
   - repair logic now updates row-level YTD and `total_in_words` as well.

5. **Docker restart / rebuild behavior matters.**
   - If the custom app is missing from the live environment after restart, inspect Docker image / bootstrap flow first.

---

# What remains open / next work

## Highest-priority follow-up
- re-run a full UI-only payroll cycle after any future payroll-engine changes and validate:
  - form totals
  - row-level YTD values
  - print / PDF output
  - downstream draft JE creation

## Still desirable
- add / finish `create_tax_remittance_draft_journal_entry(...)` if actual tax remittance posting should be part of the same Payroll Entry workflow
- clean up Docker bootstrap startup warnings / init-script issues so restart logs are clean
- add a formal posted / complete state on Payroll Entry if needed for operator clarity
- continue documenting exact rebuild steps for a true clean-room ERPNext install

---

# First files to inspect in a new session
- `erpnext/apps/rootedops_payroll/rootedops_payroll/services/payroll_engine.py`
- `erpnext/apps/rootedops_payroll/rootedops_payroll/api/payroll_entry_actions.py`
- `erpnext/client_scripts/payroll_entry_rootedops_payroll.js`
- `docker/docker-compose.yml`
- `docker/erpnext-custom.Dockerfile`
- `docker/erpnext-bootstrap.sh`
- `erpnext/README_SCRIPTS.md`
- `erpnext/CHATGPT_HANDOFF.md`

