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
- Deliver payslips, payroll accounting entries, and downstream cash-flow previews
- Move the normal operator workflow into standard ERPNext forms rather than bench console

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
- multi-employee validation completed successfully with balanced consolidated JE preview

### Phase 5 — Payroll Entry UI integration and hardening
Completed for current operator flow.
What was done:
- payroll engine logic copied into installed app code under `rootedops_payroll.services.payroll_engine`
- thin API wrapper added under `rootedops_payroll.api.payroll_entry_actions`
- Payroll Entry Client Script created in ERPNext and mirrored in `erpnext/client_scripts/payroll_entry_rootedops_payroll.js`
- working Payroll Entry buttons verified:
  - `Preview Attendance Payroll`
  - `Create / Refresh Draft Salary Slips`
  - `Create Consolidated Draft JE`
- hybrid overnight payroll path hardened so displayed hours and final Salary Slip summary fields are correct

### Phase 6 — Bank setup, account audit, and Payroll Cash Flow Preview
Completed for preview mode.
What was done:
- Dank Mushrooms bank defaults verified and corrected
- Raymond Danks Elevations checking and withholding bank structure created
- both companies audited for payroll expense / tax expense / payable / withholding payable / checking / withholding bank mapping
- missing account-map keys confirmed empty for both companies
- payroll engine extended with:
  - `get_default_checking_bank_gl_account(...)`
  - `get_withholding_bank_gl_account(...)`
  - `build_payroll_cash_flow_preview(...)`
  - `build_consolidated_payroll_cash_flow_preview(...)`
- Payroll Entry API extended with:
  - `preview_payroll_cash_flow(...)`
- Payroll Entry UI extended with:
  - `Preview Payroll Cash Flow`
- payroll cash-flow preview verified in UI for Dank Mushrooms after website reload

## Verified current UI operator workflow
For a saved Payroll Entry:
1. `Preview Attendance Payroll`
2. `Create / Refresh Draft Salary Slips`
3. `Create Consolidated Draft JE`
4. `Preview Payroll Cash Flow`

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
- The current cash-flow preview is a preview only. It does not yet create downstream cash-flow draft documents.
- Salary Slips should remain separate from actual bank movements. First create payroll accrual; then create employee payment and tax-reserve / remittance entries.

## Files to inspect first in the next session
- `erpnext/apps/rootedops_payroll/rootedops_payroll/services/payroll_engine.py`
- `erpnext/apps/rootedops_payroll/rootedops_payroll/api/payroll_entry_actions.py`
- `erpnext/client_scripts/payroll_entry_rootedops_payroll.js`
- `erpnext/scripts/README_SCRIPTS.md`
- `erpnext/README.md`

## Next starting point
Once this preview is working, the next step should be two more server actions, not just one:
- `create_employee_payment_draft_journal_entry`
- `create_tax_reserve_transfer_draft_journal_entry`

That way the UI can move from preview to actual cash-flow documents in the same pattern as the existing consolidated accrual JE button.
