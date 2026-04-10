# RootedOps ERPNext Payroll Handoff

## Project
RootedOps / `erpnext/` folder

## Environment
- Frappe: 16.11.0
- ERPNext: 16.9.1
- HRMS: 16.4.3
- employee_self_service: 2.2.2
- rootedops_payroll app installed in the live ERPNext environment

## High-level goals
- Track attendance from check-in / check-out
- Run payroll for Dank Mushrooms, LLC without an outside payroll processor
- Run payroll for Raymond Danks household / nanny use case
- Deliver Salary Slips, payroll accounting entries, and downstream cash-flow previews from Payroll Entry
- Keep the normal operator workflow inside ERPNext UI rather than bench console
- Keep Docker rebuild / restart behavior from dropping the custom app

## Completed phases

### Phase 1 — Attendance foundation
Completed.
- Day Shift created and validated
- Auto attendance enabled
- Shift logic changed to use explicit log types
- Shift Assignment created and submitted
- Clean checkins now produce Attendance with working_hours

### Phase 2 — Hourly payroll foundation
Completed.
- Payroll Settings changed from leave-based to attendance-based payroll
- Stock weekly salary-structure proration model was tested and rejected for this use case
- A custom attendance-driven hourly payroll path was implemented
- The custom path reliably calculates gross wages, employee FICA, employer FICA, and draft Salary Slips

### Phase 3 — Withholding automation, employee tax profiles, and draft accrual Journal Entry creation
Completed.
What now works:
- sums `Attendance.working_hours`
- calculates gross as hours × hourly rate
- calculates employee and employer FICA
- calculates 2026 federal weekly withholding
- calculates 2026 Colorado withholding
- stores employee federal / Colorado tax profile values on Employee custom fields
- stores hourly rate on Employee custom field
- generates liability summary, payroll register, and draft accrual JE preview

### Phase 4 — Batched payroll-period runs and consolidated accrual JE support
Completed.
What now works:
- `run_batched_hourly_payroll(...)`
- one Salary Slip per employee in a pay period
- consolidated payroll register output
- consolidated liability summary output
- consolidated accrual JE preview and draft creation

### Phase 5 — Payroll Entry UI integration and hybrid-overnight hardening
Completed.
What was done:
- payroll engine logic moved into installed app code under `rootedops_payroll.services.payroll_engine`
- thin API layer added under `rootedops_payroll.api.payroll_entry_actions`
- Payroll Entry Client Script created in ERPNext and mirrored in `erpnext/client_scripts/payroll_entry_rootedops_payroll.js`
- working Payroll Entry buttons verified for preview, draft slips, and draft accrual JE creation
- hybrid overnight payroll implemented and hardened
- payroll-period boundary handling corrected so post-boundary hours are excluded from the prior run and captured by the next run

### Phase 6 — Cash-flow workflow, live payroll execution, submit hardening, and app persistence
Mostly completed.

#### 6A — Bank setup, account audit, and cash-flow preview
Completed.
- Dank Mushrooms bank defaults verified and corrected
- Raymond Danks checking / withholding bank structure created
- both companies audited for payroll account mapping and bank GLs
- cash-flow preview builders added
- Payroll Entry UI button `Preview Payroll Cash Flow` verified

#### 6B — Downstream cash-flow draft JE actions
Completed.
- `create_employee_payment_draft_journal_entry(...)`
- `create_tax_reserve_transfer_draft_journal_entry(...)`
- Payroll Entry custom JE-link fields added / repaired
- preview-schema mismatch fixed by normalizing downstream JE preview payload shape

#### 6C — First live payroll cycles and submit hardening
Completed for the current UI-first flow.
- first live Raymond Danks payroll cycle validated through Salary Slip and downstream JEs
- first live Dank Mushrooms payroll cycle used as the reference case for submit-hardening and print-format drift
- Holiday List Assignment requirement for HRMS Salary Slip submit discovered and documented
- Payroll Entry UI action `Submit Draft Salary Slips` added
- `submit_custom_salary_slip(...)` now snapshots row values and summary values, submits, restores controlled fields, then finalizes
- `repair_salary_slip_totals(...)` now repairs:
  - gross / deduction / net / rounded totals
  - YTD / MTD header fields
  - `total_in_words`
  - row-level `Salary Detail.year_to_date`
- `ytd_gross_before_period(...)` corrected to count submitted slips only

#### 6D — Docker/app persistence
Completed enough for normal use.
- `rootedops_payroll` now persists through clean Docker rebuild / restart when repo Docker files are used
- `payments` removed from filesystem and `sites/apps.txt`
- verified live loaded source for:
  - `submit_draft_salary_slips(...)`
  - `submit_custom_salary_slip(...)`
  - `repair_salary_slip_totals(...)`

## Verified current UI operator workflow
For a saved Payroll Entry:
1. `Preview Attendance Payroll`
2. `Create / Refresh Draft Salary Slips`
3. inspect draft Salary Slips if desired
4. `Submit Draft Salary Slips` (**RootedOps button**, not native Salary Slip submit)
5. verify Salary Slip form values and PDF / print output
6. `Create Consolidated Draft JE`
7. `Preview Payroll Cash Flow`
8. `Create Employee Payment Draft JE`
9. `Create Tax Reserve Transfer Draft JE`
10. review and submit accounting docs in ERPNext

## Verified bank setup
### Dank Mushrooms, LLC
- default bank account: `Dank Mushrooms Checking - High Plains Bank`
- checking GL: `Dank Mushrooms Checking - DML`
- withholding GL: `Dank Mushrooms Withholding - DML`

### Raymond Danks
- default bank account: `Raymond Danks Elevations Checking - Elevations Credit Union`
- checking GL: `Elevations Checking - RD`
- withholding GL: `Elevations Withholding Savings - RD`

## Verified payroll account map
### Dank Mushrooms, LLC
- payroll expense: `Payroll Expense - DML`
- payroll tax expense: `Payroll Tax Expense - DML`
- payroll payable: `Payroll Payable - DML`
- payroll tax payable: `Payroll Tax Payable - DML`
- payroll withholding payable: `Payroll Withholding Payable - DML`

### Raymond Danks
- payroll expense: `Nanny Wages - RD`
- payroll tax expense: `Payroll Tax Expense - RD`
- payroll payable: `Payroll Payable - RD`
- payroll tax payable: `Payroll Tax Payable - RD`
- payroll withholding payable: `Payroll Withholding Payable - RD`

## Important operational notes
- Reload the website after client-script or app-code updates before assuming the UI is broken.
- The current cash-flow preview is no longer the end-state; downstream draft JE actions are part of the intended workflow.
- Salary Slips should be submitted through the RootedOps Payroll Entry action, not the native Salary Slip button.
- PDF / print drift was traced to stale row-level YTD and stale `total_in_words`; those are now repaired in app code.
- Holiday List Assignment is required for Salary Slip submit on this install.

## Files to inspect first in the next session
- `erpnext/apps/rootedops_payroll/rootedops_payroll/services/payroll_engine.py`
- `erpnext/apps/rootedops_payroll/rootedops_payroll/api/payroll_entry_actions.py`
- `erpnext/client_scripts/payroll_entry_rootedops_payroll.js`
- `docker/docker-compose.yml`
- `docker/erpnext-custom.Dockerfile`
- `docker/erpnext-bootstrap.sh`
- `erpnext/README.md`
- `erpnext/README_SCRIPTS.md`

## Next starting point
The major Phase 6 work is now in place. The next session should start by:
1. confirming one more clean UI-only payroll cycle after the latest `repair_salary_slip_totals(...)` patch,
2. deciding whether to add `create_tax_remittance_draft_journal_entry(...)`,
3. cleaning any remaining Docker init/bootstrap warnings,
4. and then stabilizing docs / rebuild instructions for a future clean-room install.
