# RootedOps ERPNext Scripts, App Code, and UI Workflow Guide

This file is the **implementation and operations guide** for the ERPNext folder.

It intentionally covers more than the `scripts/` directory alone, because the current payroll workflow spans:
- helper scripts in `scripts/`
- installed app code in `apps/rootedops_payroll/`
- Client Script behavior mirrored in `client_scripts/`
- ERPNext database state that those artifacts operate against

If `README.md` answers **what this project is and where it stands**, this file answers **how it works and how to operate it**.

---

# Code ownership map

## 1. Helper scripts in `scripts/`
These are bench-oriented setup, repair, or validation helpers.

## 2. App code in `apps/rootedops_payroll/`
This is the reusable custom payroll layer used by the Payroll Entry UI.

## 3. Client Script in `client_scripts/`
This is the ERPNext-side UI behavior reference. The live version exists in the ERPNext database; the repo file is the source-controlled mirror.

## 4. ERPNext database state
This includes:
- Company defaults
- Salary Components and company account rows
- Bank Account masters
- Client Script records
- Custom Fields
- Payroll Entry records
- Salary Slips and Journal Entries

A troubleshooting session often requires checking all four layers.

---

# Script and module inventory

## `scripts/10_setup_master_data.py`
Use for:
- cost centers
- departments
- designations
- supporting master data

## `scripts/20_setup_shift_and_test_employee.py`
Use for:
- Payroll Settings baseline
- Day Shift setup
- initial test employee setup
- submitted Shift Assignment creation

## `scripts/21_create_employee.py`
Preferred helper for creating a payroll-ready employee with fewer manual misses.

Current responsibilities:
- create or update Employee
- create or update linked User
- set payroll custom fields
- create submitted Shift Assignment
- optionally create Salary Structure Assignment
- provide clean test checkin helpers

## `scripts/30_create_employee_home_page.py`
Creates the file-backed employee landing page used when Workspace behavior was unreliable.

## `scripts/40_setup_payroll_test_foundation.py`
Creates or repairs the payroll test foundation, including salary structure / assignment expectations used by the payroll engine.

## `scripts/50_hourly_payroll_automation.py`
This is the **bench-readable reference implementation** for the payroll engine.

It remains valuable even though the UI now calls into the extracted app module.

Current functional scope includes:
- attendance-driven hourly payroll
- FICA
- federal withholding for supported weekly logic
- Colorado withholding
- employee tax-profile persistence
- single-slip rebuild flow
- batched payroll runs
- consolidated payroll register output
- consolidated liability summary
- consolidated accrual JE preview and draft creation
- cash-flow preview helpers

## `scripts/60_setup_payroll_entry_ui_support.py`
Creates or repairs custom Payroll Entry fields used by the UI integration.

## `scripts/61_add_salary_slip_hours_field.py`
Creates or repairs Salary Slip fields needed so final hours or hybrid totals are preserved visibly.

## `scripts/70_phase6_bank_setup.py`
Creates or repairs bank setup and default-bank configuration required for payroll cash-flow logic.

## `scripts/71_phase6_payroll_account_audit.py`
Audits payroll account mapping and bank linkage for the supported companies.

---

# App-layer inventory

## `apps/rootedops_payroll/rootedops_payroll/services/payroll_engine.py`
This is the main reusable payroll engine used by the Payroll Entry UI and should be treated as the app-side source of truth for live behavior.

Major responsibilities:
- attendance resolution
- pay-model handling
- draft Salary Slip build / refresh
- consolidated payroll preview
- consolidated accrual JE preview / draft creation
- payroll cash-flow preview
- bank-account lookup helpers

## `apps/rootedops_payroll/rootedops_payroll/api/payroll_entry_actions.py`
Thin API layer exposing whitelisted actions for the Payroll Entry UI.

Current or recent action pattern includes:
- payroll preview
- draft slip creation / refresh
- consolidated draft accrual JE creation
- payroll cash-flow preview
- upcoming downstream cash-flow draft creation actions

## `apps/rootedops_payroll/rootedops_payroll/hooks.py`
App hook configuration. Verify this when client-side code or whitelisted methods appear not to load.

---

# UI-layer inventory

## `client_scripts/payroll_entry_rootedops_payroll.js`
This file mirrors the current live Payroll Entry Client Script.

Use it to:
- review current button behavior
- restore the Client Script in ERPNext if needed
- compare repo state to live database state

Current verified button set:
- `Preview Attendance Payroll`
- `Create / Refresh Draft Salary Slips`
- `Create Consolidated Draft JE`
- `Preview Payroll Cash Flow`

Important:
- after app or Client Script changes, reload the website before concluding the Payroll Entry form is broken

---

# Recommended execution pattern for helper scripts

From the project root on the host, copy the script into the ERPNext backend container:

```bash
sudo docker cp erpnext/scripts/50_hourly_payroll_automation.py \
  erpnext-backend:/home/frappe/frappe-bench/sites/50_hourly_payroll_automation.py
```

Open bench console:

```bash
sudo docker compose --env-file ./.env -f docker/docker-compose.yml exec erpnext-backend \
  bash -lc "bench --site erp.danks.store console"
```

Load the script:

```python
exec(open("/home/frappe/frappe-bench/sites/50_hourly_payroll_automation.py").read(), globals())
```

This copy-and-load pattern remains the safest method for larger helpers.

---

# Current operator workflow from Payroll Entry

For a saved Payroll Entry:
1. click `Preview Attendance Payroll`
2. review writeback fields and preview output
3. click `Create / Refresh Draft Salary Slips`
4. review the created or refreshed draft Salary Slips
5. click `Create Consolidated Draft JE`
6. review the payroll accrual JE
7. click `Preview Payroll Cash Flow`
8. review the intended downstream checking / withholding / remittance flow

This is the current normal workflow.

Bench-console work should mainly be used for:
- setup
- repair
- audit
- debugging
- test data generation

---

# Accounting model currently assumed by the payroll logic

## Accrual step
Payroll accrual creates:
- wage expense
- employer payroll tax expense
- payroll payable liability
- payroll tax payable liability
- payroll withholding payable liability

## Cash-movement step
Downstream cash movement should remain separate:
- employee payment from checking
- reserve transfer from checking to withholding bank
- tax remittance from withholding bank

This separation is intentional.

Do not merge the accrual JE and the cash-movement JE into one document unless the accounting model is intentionally redesigned.

---

# Company/account configuration expectations

## Dank Mushrooms, LLC
Expected payroll account map:
- `Payroll Expense - DML`
- `Payroll Tax Expense - DML`
- `Payroll Payable - DML`
- `Payroll Tax Payable - DML`
- `Payroll Withholding Payable - DML`

Expected bank mapping:
- default bank account: `Dank Mushrooms Checking - High Plains Bank`
- checking GL: `Dank Mushrooms Checking - DML`
- withholding GL: `Dank Mushrooms Withholding - DML`

## Raymond Danks
Expected payroll account map:
- `Nanny Wages - RD`
- `Payroll Tax Expense - RD`
- `Payroll Payable - RD`
- `Payroll Tax Payable - RD`
- `Payroll Withholding Payable - RD`

Expected bank mapping:
- default bank account: `Raymond Danks Elevations Checking - Elevations Credit Union`
- checking GL: `Elevations Checking - RD`
- withholding GL: `Elevations Withholding Savings - RD`

## Rooted Psyche
Not yet validated to the same operational depth.
Before production payroll use, confirm:
- payroll expense / liability accounts
- Salary Component Account rows
- bank-account structure
- salary structure / assignments
- end-to-end Payroll Entry and JE testing

---

# Payroll employee onboarding

## UI-first path
Recommended when a normal operator should understand the process.

1. create Employee
2. create submitted Shift Assignment
3. create submitted Salary Structure Assignment
4. populate payroll custom fields
5. enter checkins
6. process attendance
7. verify Attendance with working hours before payroll

## Bench-assisted path
Recommended when you want the most reliable setup with less clicking.

Use `scripts/21_create_employee.py`.

Typical flow:

```bash
sudo docker cp erpnext/scripts/21_create_employee.py \
  erpnext-backend:/home/frappe/frappe-bench/sites/21_create_employee.py
```

```bash
sudo docker compose --env-file ./.env -f docker/docker-compose.yml exec erpnext-backend \
  bash -lc "bench --site erp.danks.store console"
```

```python
exec(open("/home/frappe/frappe-bench/sites/21_create_employee.py").read(), globals())
```

Then call `create_or_update_employee(...)` with the company, shift, salary structure, pay rate, and tax profiles you need.

### Hybrid employee note
For hybrid overnight employees, always verify:
- `rootedops_pay_model`
- `rootedops_overnight_flat_amount`

after creation.

---

# Test attendance creation

Use the helper from `21_create_employee.py`:

```python
insert_checkin_pair("HR-EMP-00006", "2026-03-29 09:00:00", "2026-03-29 17:00:00")
```

For overnight tests:

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

Before payroll, verify that submitted Attendance exists and has nonzero `working_hours` where expected.

---

# Useful payroll-engine helpers

The exact callable surface may evolve, but the important working patterns include:
- employee tax-profile update and retrieval
- one-slip rebuild for one employee / one period
- batched payroll run for one company / pay period
- consolidated liability summary
- consolidated accrual JE preview / draft creation
- payroll cash-flow preview
- employee discovery from attendance in a date range

Typical examples from the bench reference layer include:
- `update_employee_tax_profile(...)`
- `get_employee_tax_profile(...)`
- `rebuild_hourly_salary_slip(...)`
- `run_batched_hourly_payroll(...)`
- `build_consolidated_payroll_journal_entry_preview(...)`
- `create_consolidated_payroll_journal_entry_draft(...)`
- `get_employees_with_attendance_in_period(...)`

As Phase 6 continues, additional draft-JE creation helpers should join that pattern.

---

# Troubleshooting guide

## Buttons missing or behaving oddly in Payroll Entry
Check in this order:
1. website reload performed?
2. Client Script in ERPNext matches `client_scripts/payroll_entry_rootedops_payroll.js`?
3. app code deployed and reloaded?
4. hooks loading correctly?
5. whitelisted method path still valid?

## Employee has checkins but payroll shows zero hours
Check:
1. Shift Assignment exists and is submitted
2. checkins use explicit `IN` / `OUT`
3. `skip_auto_attendance = 0`
4. Attendance rows were actually created
5. Attendance rows have nonzero `working_hours`

## Salary Slip rebuild fails
Check:
1. Salary Structure Assignment exists and is submitted
2. employee custom fields are present
3. hourly rate is populated
4. company account map is complete
5. Salary Component Account rows exist for the company

## Consolidated JE preview is incomplete or not ready
Check:
1. all payroll results belong to one company
2. all required payroll account map keys resolve
3. gross / deductions / employer tax values are nonzero where expected
4. missing-account list is empty

## UI looks current but server behavior looks old
Likely causes:
- app code not reloaded
- stale website assets
- live Client Script differs from repo mirror
- live ERPNext database state differs from expected setup

---

# Validation checklists

## Before using a real employee
- Employee exists and is active
- submitted Shift Assignment exists
- submitted Salary Structure Assignment exists
- payroll custom fields are populated
- Attendance exists with working hours
- payroll account map is complete
- relevant Salary Component Account rows exist
- default bank account is configured if cash-flow features will be used

## Before trusting Payroll Entry UI changes
- app code matches intended snapshot
- Client Script matches intended snapshot
- helper Custom Fields exist
- browser / website reload completed
- test Payroll Entry successfully previews and writes back results

## Before a fresh-install handoff is considered reproducible
- baseline CSV imports documented
- required helper scripts documented
- app installation documented
- required ERPNext UI setup documented
- company-specific account and bank requirements documented
- at least one full payroll dry run validated

---

# Year-bound maintenance notes

Before the first payroll of a new calendar year, review and update:
- FICA wage base
- any FICA rate changes
- federal withholding tables / logic
- Colorado withholding constants / logic
- any W-4 or Colorado form interpretation changes

Then rerun a validation payroll test and confirm:
- gross
- deductions
- employer taxes
- net pay
- liability summary
- JE preview balance
- cash-flow preview logic

---

# Immediate next implementation target

Proceed with **Phase 6B** by adding server/UI actions for:
- `create_employee_payment_draft_journal_entry`
- `create_tax_reserve_transfer_draft_journal_entry`

Once those exist, update this file with:
- where the actions live
- what documents they create
- what review steps the operator must follow
- how those entries interact with the accrual JE and cash-flow preview

---

# See also

- `README.md`
- `CHATGPT_HANDOFF.md`
- `CHATGPT_HANDOFF.json`
