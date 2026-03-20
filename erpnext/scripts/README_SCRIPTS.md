# RootedOps ERPNext Scripts

These scripts are meant to be loaded into `bench --site erp.danks.store console`.

## General pattern

Copy the script into the ERPNext container:

```bash
sudo docker cp erpnext/scripts/<scriptname>.py   erpnext-backend:/home/frappe/frappe-bench/sites/<scriptname>.py
```

Open bench console:

```bash
sudo docker compose --env-file ./.env -f docker/docker-compose.yml exec erpnext-backend   bash -lc "bench --site erp.danks.store console"
```

Load the file:

```python
exec(open("/home/frappe/frappe-bench/sites/<scriptname>.py").read(), globals())
```

## Script purposes

### `10_setup_master_data.py`
Creates or updates:
- payroll-related cost centers
- departments
- designations
- helper accounts if they already exist in the company chart structure

### `20_setup_shift_and_test_employee.py`
Creates or updates:
- Payroll Settings
- Day Shift
- test employee
- submitted Shift Assignment
- clean test checkins (optional helper)

### `30_create_employee_home_page.py`
Creates the file-backed Desk page:
- `employee-home`
- assets under `apps/hrms/hrms/hr/page/employee_home`

### `40_setup_payroll_test_foundation.py`
Creates or repairs:
- test salary structure
- test salary structure assignment

### `50_hourly_payroll_automation.py`
Provides:
- attendance-driven hourly payroll helper
- employee FICA
- employer FICA
- draft salary slip rebuilding

## Notes
These scripts are designed to be idempotent or close to it, but they should still be reviewed before running in production.
