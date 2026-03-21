# RootedOps ERPNext Payroll Handoff

## Project
RootedOps / `erpnext/` folder

## Environment
- Frappe: 16.11.0
- ERPNext: 16.9.1
- HRMS: 16.4.3
- employee_self_service: 2.2.2

## High-level goals
- Track attendance from check-in / check-out
- Run payroll for Dank Mushrooms, LLC without an outside payroll processor
- Support an ad-hoc hourly W-2 employee who may work weekends
- Deliver payslips, backend payroll records, and accounting entries
- Later onboard a real employee using actual W-4 and Colorado withholding data

## What has been completed

### Phase 1 — Attendance foundation
Completed.

- Day Shift created and validated
- Auto attendance enabled
- Shift logic changed to use explicit log types
- Shift Assignment created and submitted
- Clean checkins now produce Attendance with working_hours

Verified attendance state:
- 2026-03-16 = Present, 8.0 hours
- 2026-03-17 = Present, 8.0 hours
- 2026-03-15 = Absent, 0.0 hours (test artifact)

### Phase 2 — Hourly payroll foundation
Completed.

- Payroll Settings changed from leave-based to attendance-based payroll
- Stock weekly salary-structure proration model was tested and rejected for this use case
- A custom attendance-driven hourly payroll script was implemented

Confirmed diagnosis of the old wrong-net-pay result:
- ERPNext was still applying the submitted Salary Structure during Salary Slip calculation
- The test structure earning `800.00` with `depends_on_payment_days = 1` was being prorated to `228.57`
- `228.57 - 19.84 SS - 4.64 Medicare = 204.09`
- The custom gross of `320.00` was not the value driving final net pay until the custom path was corrected

### Phase 3 — Withholding automation, employee tax profiles, and draft Journal Entry creation
Completed.

What now works:
- sums Attendance.working_hours
- calculates gross as hours * hourly_rate
- calculates employee Social Security and Medicare
- calculates employer Social Security and Medicare
- calculates federal withholding for 2026 weekly payroll using stored W-4 style inputs
- calculates Colorado withholding for 2026 using stored DR 1098 / DR 0004 style inputs
- stores hourly rate and tax-profile defaults on Employee custom fields
- rebuilds a draft Salary Slip with those values
- generates payroll liability summary
- generates payroll register row
- generates Journal Entry preview
- creates draft Journal Entry successfully

### Phase 4 — Payroll batching and consolidated Journal Entry workflow
Completed and validated through a clean four-employee payroll batch.

What is now implemented:
- batches multiple employee salary-slip rebuilds into one payroll-period run
- supports attendance-driven employee discovery for a date range
- generates consolidated payroll register output for the run
- generates consolidated payroll liability summary for the run
- generates one consolidated payroll Journal Entry preview for the run
- creates one consolidated draft Journal Entry for the run
- preserves the single-slip workflow for debugging and employee-level review

## Latest successful verified multi-employee test result

### Four-employee validation run
Company: `Dank Mushrooms, LLC`
Pay period: `2026-03-15` to `2026-03-21`

### Employee results from the clean four-employee batch
- `HR-EMP-00001` → Gross `400.00`, Net `347.45`
- `HR-EMP-00002` → Gross `472.50`, Net `403.96`
- `HR-EMP-00003` → Gross `258.75`, Net `232.23`
- `HR-EMP-00004` → Gross `600.00`, Net `502.31`

### Consolidated batch result for period `2026-03-15` to `2026-03-21`
- employee_count: `4`
- consolidated Journal Entry preview balanced: `True`
- all four employees produced non-zero payroll results
- auto-attendance preprocessing and payroll prerequisite diagnostics are active in the current script

### Important hardening findings from validation
- Older employee records created before the onboarding script fix may need payroll-field backfill.
- Checkins with `skip_auto_attendance = 1` will prevent attendance-driven payroll and now fail fast in the payroll script.
- Reprocessing attendance may require cancelling/deleting existing Attendance rows before rerunning `Shift Type.process_auto_attendance()`.

### Operational status
The payroll logic itself is now working. The remaining work should move out of ad-hoc bench-console testing and into ERPNext UI / automation flow design so the operator can review and run payroll from the application rather than living in bench console.

## What scripts now exist

### `scripts/10_setup_master_data.py`
Creates basic departments, designations, and payroll-related cost centers/master data.

### `scripts/20_setup_shift_and_test_employee.py`
Creates/updates Payroll Settings, Day Shift, test employee, and submitted Shift Assignment.

### `scripts/30_create_employee_home_page.py`
Creates the custom Desk page `employee-home`.

### `scripts/40_setup_payroll_test_foundation.py`
Creates the clean salary structure and assignment used for payroll testing and payroll-ready onboarding.

### `scripts/50_hourly_payroll_automation.py`
Main payroll automation script. Current scope includes:
- attendance-based hourly payroll
- FICA
- federal withholding
- Colorado withholding
- employee tax-profile storage
- liability summary
- payroll register row
- JE preview
- draft JE creation
- batched payroll-period runs
- consolidated payroll register output
- consolidated JE preview
- consolidated draft JE creation

## Important lessons learned
- Default shift on Employee was not enough; submitted Shift Assignment mattered.
- `last_sync_of_checkin` had to be moved far enough forward for historical auto attendance tests.
- Pasting large scripts into bench console was unreliable.
- Best pattern is:
  1. copy script into container with `docker cp`
  2. load with `exec(open(...).read(), globals())`
- Colorado DR 0004 line 2 handling needed a separate override checkbox because the field itself may not be nullable in this site.
- Salary Slip custom rows needed to be normalized after save so `depends_on_payment_days = 0` persisted.
- JE account rows in this ERPNext site cannot use `reference_type = "Salary Slip"`.

## Current ERPNext configuration that should remain
- Payroll Settings:
  - `payroll_based_on = Attendance`
  - `consider_unmarked_attendance_as = Absent`
- Company default payroll payable account:
  - `Payroll Payable - DML`
- Payroll accounts:
  - `Payroll Expense - DML`
  - `Payroll Tax Expense - DML`
  - `Payroll Payable - DML`
  - `Payroll Tax Payable - DML`
  - `Payroll Withholding Payable - DML`

## Operational update procedures already supported by the current script

### Annual tax-table update
At the beginning of a new year, update:
- federal weekly withholding tables
- Social Security wage base
- Colorado rate / subtraction values / DR 1098 logic

Then rerun a payroll validation test before first real payroll.

### Employee hourly-rate change
Update the stored Employee rate, then rerun a payroll validation test.

### New W-4
Map the W-4 into the stored Employee federal profile fields, then rerun payroll validation.

### New Colorado withholding form
Map the Colorado values into the stored Employee Colorado profile fields, then rerun payroll validation.

## Current phase status
Phase 4 — payroll batching and operationalization is now in progress.

Completed in this step:
1. batch multiple salary slips into one payroll-period run
2. create consolidated payroll register output
3. create one consolidated Journal Entry preview for a payroll period
4. create one consolidated draft Journal Entry for a payroll period

Recommended next work:
1. add duplicate-run safeguards around consolidated JE creation
2. add stronger validation / reconciliation helpers
3. decide whether to introduce Payroll Entry objects or stay on the custom scripted path
4. document a first real employee onboarding procedure using actual W-4 and Colorado inputs
5. document an operator checklist for running each payroll period

## Suggested opening request for the next ChatGPT session
"""
Continue RootedOps ERPNext payroll Phase 4. Phase 4 batching basics are now implemented in `erpnext/scripts/50_hourly_payroll_automation.py`, including `run_batched_hourly_payroll()`, consolidated register output, and consolidated Journal Entry preview/draft creation. Review `erpnext/CHATGPT_HANDOFF.md`, `erpnext/CHATGPT_HANDOFF.json`, `erpnext/README.md`, `erpnext/scripts/README_SCRIPTS.md`, and `erpnext/scripts/50_hourly_payroll_automation.py`. Next, harden the payroll-period workflow with reconciliation checks, duplicate-run safeguards, and an operator checklist.
"""

## Phase 4 update in progress

The project has started Phase 4 by adding batched payroll-period helpers to `scripts/50_hourly_payroll_automation.py` so multiple salary slips can be processed into one consolidated Journal Entry preview/draft.

Before validating the multi-employee path, use `scripts/21_create_employee.py` to create an additional payroll-test employee with:
- linked User
- Employee master record
- default shift
- submitted Shift Assignment
- optional hourly rate and federal/Colorado tax-profile custom fields

Recommended next sequence:
1. create second test employee with `21_create_employee.py`
2. record checkins / attendance for both employees in the same payroll week
3. run `run_batched_hourly_payroll(...)`
4. verify consolidated JE grouping, totals, and balancing across multiple salary slips
5. only after that, continue into payment/disbursement helpers


## Phase 4 validation update
- Two-employee batched payroll validation succeeded after processing auto attendance and supplying employee 2 payroll profile values.
- Confirmed combined liability summary for employees HR-EMP-00001 and HR-EMP-00002 for 2026-03-15 through 2026-03-21: gross wages 668.75, net pay 592.59, employer tax total 51.16, balanced consolidated JE.
- Employee onboarding gap found: `21_create_employee.py` originally wrote the wrong custom fieldnames and did not create a Salary Structure Assignment. Patch this before validating a third employee.
- Payroll run gap found: batched payroll should process auto attendance before reading attendance-based hours. Patch this before validating a third employee.


## Phase 4 validation update - three employees successful
- A full three-employee payroll batch was validated for `2026-03-15` through `2026-03-21`.
- Verified salary-slip results:
  - `HR-EMP-00001` gross `400.00`, net `347.45`
  - `HR-EMP-00002` gross `472.50`, net `403.96`
  - `HR-EMP-00003` gross `258.75`, net `232.23`
- Consolidated payroll-period JE preview remained balanced.
- The onboarding helper now created a payroll-ready third employee without manual salary-structure or custom-field fixes.
- Remaining hardening added afterward:
  - detect zero or missing hourly rate earlier
  - detect checkins with `skip_auto_attendance = 1`
  - detect employees with checkins in period but zero resolved attendance hours
  - provide a helper to backfill payroll setup on older employees created before the onboarding fixes
  - provide a helper to create clean IN/OUT checkin pairs with auto attendance enabled

## Recommended next validation
Use the documented fourth-employee checklist in `erpnext/README.md` and `erpnext/scripts/README_SCRIPTS.md`:
1. create `HR-EMP-00004` with `create_or_update_employee(...)`
2. create clean checkins with `insert_checkin_pair(...)`
3. process auto attendance
4. run `run_batched_hourly_payroll(...)` for employees 1 through 4
5. confirm all four salary slips show nonzero gross and net and the consolidated JE preview is balanced

## Recommended next phase after this handoff

### Phase 5 — UI and automation-hook integration
Primary goal: stop depending on bench-console execution for normal payroll operations.

Recommended work items:
- expose the current payroll flow behind ERPNext UI actions or server hooks
- decide what the operator should do in the UI each pay period and what should happen automatically
- make payroll results visible from ERPNext forms the operator already uses
- add explicit review / approval points before creating accounting entries or payments
- add payment-entry / reserve-transfer helpers after payroll accrual review

Recommended ERPNext integration points to evaluate in the next session:
- a custom button on `Salary Slip`, `Payroll Entry`, or a custom DocType for weekly payroll runs
- a server-side whitelisted method that wraps `run_batched_hourly_payroll(...)`
- optional scheduled / hook-based attendance preprocessing before payroll
- a custom DocType or page to store payroll-run metadata, consolidated JE references, review status, and operator notes
- clear UI links from the payroll run to Salary Slips, Journal Entry draft, and liability totals
