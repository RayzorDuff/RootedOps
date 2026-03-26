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
- Support an ad-hoc hourly W-2 employee who may work weekends
- Deliver payslips, backend payroll records, and accounting entries
- Move the normal operator workflow into standard ERPNext forms rather than bench console
- Later onboard real employees using actual W-4 and Colorado withholding data

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
- A custom attendance-driven hourly payroll script was implemented
- The custom path now reliably calculates gross wages, employee FICA, employer FICA, and draft Salary Slips

### Phase 3 — Withholding automation, employee tax profiles, and draft Journal Entry creation
Completed.

What now works:
- sums `Attendance.working_hours`
- calculates gross as hours × hourly rate
- calculates employee and employer FICA
- calculates 2026 federal weekly withholding
- calculates 2026 Colorado withholding
- stores employee federal / Colorado tax profile values on Employee custom fields
- stores hourly rate on Employee custom field
- rebuilds one draft Salary Slip for the employee / period
- generates one payroll liability summary
- generates one Journal Entry preview
- can create one draft payroll accrual JE

### Phase 4 — Batched payroll-period runs and consolidated JE support
Completed.

What now works:
- `run_batched_hourly_payroll(...)`
- one Salary Slip per employee in a pay period
- consolidated payroll register output
- consolidated liability summary output
- consolidated Journal Entry preview
- consolidated draft Journal Entry creation
- four-employee validation completed successfully with balanced consolidated JE preview
- onboarding helper updated so new payroll-test employees are payroll-ready on creation
- diagnostics added for missing hourly rate, `skip_auto_attendance = 1`, and zero resolved attendance hours



### Phase 5A — Payroll engine extraction into importable app code
Completed in the live environment.

What was done:
- the logic from `scripts/50_hourly_payroll_automation.py` was copied into the installed `rootedops_payroll` app under `rootedops_payroll.services.payroll_engine`
- console import validation succeeded
- `rebuild_hourly_salary_slip(...)` and `run_batched_hourly_payroll(...)` both executed successfully from the app module

Important repo note:
- this ZIP still contains the source script in `erpnext/scripts/50_hourly_payroll_automation.py`
- the full live app tree was not present in the uploaded ZIP before this handoff update

### Phase 5B — Payroll Entry UI integration
Completed for the first working operator flow.

What was done:
- added a thin API wrapper at `rootedops_payroll.api.payroll_entry_actions`
- the wrapper now:
  - reads a saved Payroll Entry
  - derives period/company context
  - discovers employees with attendance in the period
  - previews payroll for the period
  - creates or refreshes draft Salary Slips for the period
  - creates a consolidated draft JE for the period
- a Payroll Entry Client Script was created in ERPNext with buttons for:
  - `Preview Attendance Payroll`
  - `Create / Refresh Draft Salary Slips`
  - `Create Consolidated Draft JE`

### Phase 5C — Payroll Entry writeback fields and first hardening pass
Completed.

What was done:
- created Payroll Entry custom fields:
  - `rootedops_consolidated_journal_entry`
  - `rootedops_salary_slip_count`
  - `rootedops_last_processed_on`
  - `rootedops_payroll_summary`
- preview / slip / JE actions now write summary data back onto Payroll Entry
- added duplicate consolidated JE guard:
  - if Payroll Entry already contains `rootedops_consolidated_journal_entry`, the JE action throws instead of creating another accrual JE

## Latest verified working UI state
Using `Payroll Entry HR-PRUN-2026-00001` for `2026-03-15` to `2026-03-21`:

- preview button worked
- draft Salary Slip creation / refresh worked
- consolidated draft Journal Entry creation worked
- Payroll Entry custom fields populated in the UI

## Latest verified payroll results
For period `2026-03-15` to `2026-03-21`:

- `HR-EMP-00001` gross/net: `400.00 / 347.45`
- `HR-EMP-00002` gross/net: `472.50 / 403.96`
- `HR-EMP-00003` gross/net: `258.75 / 232.23`
- `HR-EMP-00004` gross/net: `600.00 / 502.31`

Consolidated JE preview remained balanced.

## Files now relevant in the repo
- `erpnext/scripts/21_create_employee.py`
- `erpnext/scripts/50_hourly_payroll_automation.py`
- `erpnext/scripts/60_setup_payroll_entry_ui_support.py`
- `erpnext/scripts/README_SCRIPTS.md`
- `erpnext/client_scripts/payroll_entry_rootedops_payroll.js`
- `erpnext/apps/rootedops_payroll/rootedops_payroll/api/payroll_entry_actions.py`

## Known packaging gap
The live environment now contains more `rootedops_payroll` app content than this repo previously captured. The next repo export should include the full app tree so the UI/server integration is fully versioned in Git and not only present in the live container.

## Recommended next phase

### Phase 5D — Salary Slip hardening and operator polish
Primary goal: make the current UI flow safer and clearer before normal live use.

Recommended work items:
- explicitly detect submitted Salary Slips already existing for the same employee + period and block duplicate processing
- make draft-slip refresh behavior more explicit and operator-visible
- improve button popup messages with direct links to Salary Slips and the Journal Entry
- optionally add a clearer override path later if a JE must be intentionally regenerated

### Phase 6 — Payment / bank / reconciliation workflow
After Phase 5D:
- document the bank ledger and Bank Account mapping for payroll cash disbursement
- document or script the Payment Entry workflow for wages, payroll taxes, and withholding remittance
- add reserve-transfer helpers only if they still look useful after the standard accounting workflow is exercised
