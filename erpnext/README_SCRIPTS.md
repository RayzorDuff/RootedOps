# RootedOps ERPNext Scripts, App Code, and Operator Workflow Reference

This file captures the exact purpose of the helper scripts, installed app code, client-script/UI actions, validation paths, and operational troubleshooting patterns for the ERPNext payroll workflow.

It intentionally preserves older setup history while reflecting the current UI-first operator model.

---

# Core implementation layers

The current ERPNext payroll workflow spans four layers:

1. **Bootstrap/import artifacts**
   - CSVs and seed files used for fresh ERPNext setup

2. **Bench/helper scripts**
   - one-time or occasional setup / audit / repair helpers

3. **Installed custom app (`rootedops_payroll`)**
   - live payroll engine, API, and reusable submit/finalization logic

4. **ERPNext UI / DB state**
   - Payroll Entry docs, Salary Slips, Journal Entries, Holiday Lists, bank defaults, Client Script record

---

# Bench/helper scripts

## `scripts/10_setup_master_data.py`
Use for:
- cost centers
- departments
- designations
- related master data normalization

When useful:
- clean-room rebuild
- repairing partially imported master data

## `scripts/20_setup_shift_and_test_employee.py`
Use for:
- Day Shift creation / repair
- Payroll Settings foundation
- test employee / shift assignment baseline

Historical importance:
- this created the first reliable Attendance foundation used to verify `Attendance.working_hours`.

## `scripts/21_create_employee.py`
Use for:
- creating or updating payroll-ready employee records
- user creation / linkage
- employee custom payroll fields
- shift assignment support

Still useful when:
- adding another real payroll employee
- reconstituting an employee in a clean site

## `scripts/30_create_employee_home_page.py`
Use for:
- file-backed employee landing page creation

Not central to payroll logic.

## `scripts/40_setup_payroll_test_foundation.py`
Use for:
- salary structure / salary structure assignment test baseline
- repairing early payroll-test configuration

Historical importance:
- useful as a template for rebuilding salary structures in a clean environment.

## `scripts/50_hourly_payroll_automation.py`
Use for:
- bench-reference mirror of the payroll engine logic
- historical reference for how the payroll engine evolved

Important:
- the **live app code** under `apps/rootedops_payroll/.../services/payroll_engine.py` is the operative implementation.
- this script should be treated as a reference / portability aid, not the primary runtime module.

## `scripts/60_setup_payroll_entry_ui_support.py`
Use for:
- creating / repairing Payroll Entry custom fields used by the UI flow

Important fields created / repaired include the RootedOps JE link fields and summary fields.

## `scripts/61_add_salary_slip_hours_field.py`
Use for:
- adding / repairing the custom Salary Slip hours field / related writeback support

Historical importance:
- helped keep displayed hours aligned with custom attendance payroll rather than stock ERPNext assumptions.

## `scripts/70_phase6_bank_setup.py`
Use for:
- bank-account creation / correction
- default-bank linkage setup
- checking / withholding structure for payroll cash flow

## `scripts/71_phase6_payroll_account_audit.py`
Use for:
- verifying company payroll account maps and bank GLs
- auditing readiness for payroll JE and cash-flow actions

---

# Installed app code (`apps/rootedops_payroll`)

## `services/payroll_engine.py`
This is the main payroll engine.

### Major responsibilities
- attendance-based hour collection
- hourly gross calculation
- hybrid overnight calculation
- 2026 federal withholding logic
- 2026 Colorado withholding logic
- employee/employer FICA
- consolidated liability summary
- consolidated register generation
- consolidated accrual JE preview + draft creation
- employee payment JE preview + draft creation
- tax reserve transfer JE preview + draft creation
- Salary Slip rebuild, normalization, and submit hardening
- YTD calculation for payroll-tax logic

### Important live functions

#### Attendance/pay calculation
- `hybrid_overnight_summary(...)`
- `rebuild_hourly_salary_slip(...)`
- `run_batched_hourly_payroll(...)`

#### JE preview / draft creation
- `build_consolidated_payroll_cash_flow_preview(...)`
- `create_consolidated_payroll_journal_entry_draft(...)`
- `create_consolidated_employee_payment_journal_entry_draft(...)`
- `create_consolidated_tax_reserve_transfer_journal_entry_draft(...)`

#### Salary Slip hardening
- `normalize_saved_child_rows(...)`
- `set_manual_totals(...)`
- `repair_salary_slip_totals(...)`
- `finalize_custom_salary_slip(...)`
- `submit_custom_salary_slip(...)`
- `diagnose_salary_slip_math(...)`

### Current hardening notes

#### `repair_salary_slip_totals(...)`
This function must repair **all** of the following, not just header totals:
- `gross_pay`
- `total_deduction`
- `net_pay`
- `rounded_total`
- `gross_year_to_date`
- `year_to_date`
- `month_to_date`
- `total_in_words`
- row-level `Salary Detail.year_to_date`

This is critical because the PDF / print format can expose stale child-row YTD fields even after the Salary Slip header fields look correct.

#### `submit_custom_salary_slip(...)`
This function is the UI-safe submit path.

It should:
1. snapshot earnings/deduction rows and summary fields
2. call `slip.submit()`
3. restore controlled row values / summary fields
4. call `finalize_custom_salary_slip(...)`

This is what keeps the custom payroll workflow independent from stock HRMS submit-time recalculation.

#### `ytd_gross_before_period(...)`
Must count **submitted slips only**.

Reason:
- draft/test slips were previously contaminating YTD payroll tax logic.

---

## `api/payroll_entry_actions.py`
This exposes the UI actions on Payroll Entry.

### Important whitelisted methods
- `preview_attendance_payroll(...)`
- `preview_payroll_cash_flow(...)`
- `create_or_refresh_draft_salary_slips(...)`
- `submit_draft_salary_slips(...)`
- `create_consolidated_draft_journal_entry(...)`
- `create_employee_payment_draft_journal_entry(...)`
- `create_tax_reserve_transfer_draft_journal_entry(...)`

### Critical behavior of `submit_draft_salary_slips(...)`
This function should:
- locate Salary Slips for the employee(s) and pay period
- submit draft slips through `submit_custom_salary_slip(...)`
- **not rerun payroll after submit**

The earlier bug was that it reran payroll after submit, which immediately tripped the "submitted Salary Slip already exists" safeguard.

### Notes on Payroll Entry links
The RootedOps JE link fields on Payroll Entry now matter operationally:
- `rootedops_consolidated_journal_entry`
- `rootedops_employee_payment_journal_entry`
- `rootedops_tax_reserve_transfer_journal_entry`

---

## `hooks.py`
Keep aligned with how the app is actually loaded into ERPNext, including any client JS inclusion.

---

## `public/js/payroll_entry.js`
Reference app-side JS. The DB-stored Client Script is still the working live operator reference, but this file should not drift far from it.

---

# Payroll Entry Client Script

Reference copy:
- `client_scripts/payroll_entry_rootedops_payroll.js`

## Current operator buttons
- `Preview Attendance Payroll`
- `Preview Payroll Cash Flow`
- `Create / Refresh Draft Salary Slips`
- `Submit Draft Salary Slips`
- `Create Consolidated Draft JE`
- `Create Employee Payment Draft JE`
- `Create Tax Reserve Transfer Draft JE`

## Important design note
The client script should **not** contain payroll-repair logic.

It should only call server methods.

All Salary Slip repair / YTD / PDF / submit hardening belongs in server-side Python, not in browser JS.

---

# Live operator workflow

## Salary Slip workflow
1. Create a Payroll Entry
2. `Preview Attendance Payroll`
3. `Create / Refresh Draft Salary Slips`
4. inspect draft Salary Slips if desired
5. `Submit Draft Salary Slips` using the **RootedOps button**
6. confirm Salary Slip values and PDF output

### Do not do this
- do **not** use the native Salary Slip submit button for this custom payroll workflow

Reason:
- native HRMS submit can reapply stock payroll assumptions and cause drift in YTD / print-format values.

## Journal Entry workflow
After Salary Slips are correct and submitted:
1. `Create Consolidated Draft JE`
2. `Preview Payroll Cash Flow`
3. `Create Employee Payment Draft JE`
4. `Create Tax Reserve Transfer Draft JE`
5. review and submit accounting docs in ERPNext

---

# Validation / debugging checklist

## Salary Slip draft validation
Run in bench console if needed:

```python
from rootedops_payroll.services.payroll_engine import diagnose_salary_slip_math

result = diagnose_salary_slip_math("Sal Slip/HR-EMP-00005/00003")
print(result)
```

Check:
- `gross_pay_field == earnings_sum`
- `total_deduction_field == deductions_sum`
- `net_pay_field == earnings_sum - deductions_sum`
- `depends_on_payment_days == 0` on all rows

## Salary Slip submit validation
After RootedOps UI submit:
- verify header totals
- verify YTD / MTD
- verify `total_in_words`
- verify row-level `Salary Detail.year_to_date`
- verify print / PDF output

## JE validation
For each created draft JE, confirm:
- debit = credit
- account mapping is correct
- bank GLs are correct
- Payroll Entry RootedOps JE link fields populated correctly

---

# Holiday List / HRMS submit requirements

This install requires a valid **Holiday List Assignment** for the employee for Salary Slip submit.

Important notes:
- Employee holiday_list alone was not sufficient
- the active Holiday List Assignment record was required
- assignment schema in this install used:
  - `applicable_for`
  - `assigned_to`
  - `holiday_list`
  - `from_date`
- the assignment had to be submitted to be recognized

This matters when adding new payroll employees.

---

# Docker / app persistence notes

The custom app must survive clean container recreation.

## What was happening
After a clean restart, `rootedops_payroll` disappeared from the live Python environment and had to be reinstalled with:

```bash
./env/bin/pip install -e apps/rootedops_payroll
```

That was not acceptable operationally.

## Current direction / fix
Docker files under `docker/` were updated so the custom app is included in image/build/bootstrap flow.

Files to inspect together:
- `docker/docker-compose.yml`
- `docker/erpnext-custom.Dockerfile`
- `docker/erpnext-bootstrap.sh`

## Runtime verification
After clean build/restart, verify:

```bash
bench --site erp.danks.store list-apps
```

Expected to include:
- frappe
- erpnext
- hrms
- employee_self_service
- rootedops_payroll

## Remaining watch item
During one restart sequence the logs still showed:
- `erpnext-apps-init` syntax error
- `erpnext-configurator` `mkdir: missing operand`

The runtime recovered, but Docker startup flow should still be watched and cleaned further if needed.

---

# Common failure modes and meaning

## `Submitted Salary Slip already exists ...`
Usually means:
- a slip for employee/date range is already submitted
- or the submit action incorrectly reran payroll after submit

Current fix:
- `submit_draft_salary_slips(...)` must not rerun payroll after submission

## Wrong totals after submit
Usually means:
- native HRMS submit recalculated values
- or `submit_custom_salary_slip(...)` / `repair_salary_slip_totals(...)` is stale

## PDF still wrong while bench values are correct
Usually means stale stored fields such as:
- `Salary Detail.year_to_date`
- `Salary Slip.total_in_words`

## Missing federal withholding on a low-wage slip
May be correct.
- for low weekly wages under the employee’s filing configuration, federal withholding can legitimately compute to `0.00`

## Hybrid overnight hours look short on one pay period
Check payroll-boundary splitting.
- hours after the end date should not count in the earlier period
- they should appear in the next period instead

---

# Clean next-session starting points
If a future session needs to resume work quickly, open these first:
- `apps/rootedops_payroll/rootedops_payroll/services/payroll_engine.py`
- `apps/rootedops_payroll/rootedops_payroll/api/payroll_entry_actions.py`
- `client_scripts/payroll_entry_rootedops_payroll.js`
- `README.md`
- `CHATGPT_HANDOFF.md`
- `../docker/docker-compose.yml`
---

# Quarterly Payroll Tax Report

The version-controlled report is located at:

```text
erpnext/apps/rootedops_payroll/rootedops_payroll/rootedops_payroll/report/quarterly_payroll_tax_report/
```

Deploy report metadata and code with:

```bash
sudo docker cp -a erpnext/apps/rootedops_payroll erpnext-backend:/home/frappe/frappe-bench/apps/
sudo docker compose --env-file ./.env -f docker/docker-compose.yml exec erpnext-backend \
  bash -lc "bench --site erp.danks.store migrate"
sudo docker compose --env-file ./.env -f docker/docker-compose.yml exec erpnext-backend \
  bash -lc "bench --site erp.danks.store clear-cache"
```

Search ERPNext for `Quarterly Payroll Tax Report`. Run one report per Company. For tax filing totals, use `Submitted`; use `Draft and Submitted` only for deliberate reconciliation. The quarter is selected from Salary Slip `posting_date`.

