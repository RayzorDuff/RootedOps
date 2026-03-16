
# RootedOps ERPNext Configuration Guide

This directory contains the initial configuration data and instructions for setting up ERPNext for:

- Dank Mushrooms, LLC
- Rooted Psyche

The goal of this configuration is to provide:

- basic accounting
- payroll tracking
- employee attendance
- vendor tracking
- project tracking
- asset tracking
- a simplified employee interface

---

# Directory Contents

| File | Purpose |
|-----|------|
| companies.csv | Creates Dank Mushrooms, LLC and Rooted Psyche companies |
| chart_of_accounts_dank_mushrooms_llc.csv | Dank Mushrooms Chart of Accounts |
| chart_of_accounts_rooted_psyche.csv | Rooted Psyche Chart of Accounts |
| cost_centers.csv | Cost centers used for payroll and accounting |
| departments.csv | Company departments |
| designations.csv | Employee job titles |
| employees_template.csv | Template for employee records |
| bank_accounts_template.csv | Business bank accounts |
| suppliers.csv | Vendors (Amazon, suppliers, etc.) |
| projects.csv | Projects such as farmers markets |
| expense_claim_types.csv | Expense categories |
| asset_categories.csv | Asset depreciation categories |
| RootedOps_ERPNext_Config_Pack.xlsx | Reference spreadsheet |

---

# Reset ERPNext to a Clean State (Optional)

If ERPNext already has data, wipe the site.

Stop ERPNext:

docker compose down

Remove ERPNext volumes:

docker volume rm docker_erpnext_db_data
docker volume rm docker_erpnext_sites
docker volume rm docker_erpnext_apps
docker volume rm docker_erpnext_logs

Restart ERPNext:

docker compose up -d

Run bootstrap again if necessary.

---

# Import Order (Important)

ERPNext imports must be done in the correct order.

Import using **Data Import Tool**.

Order:

1. companies.csv
2. Chart of Accounts (per company)
3. cost_centers.csv
4. departments.csv
5. designations.csv
6. bank_accounts_template.csv
7. suppliers.csv
8. projects.csv
9. expense_claim_types.csv
10. asset_categories.csv
11. employees_template.csv

---

# Create Employee

Navigate:

HR → Employee → New

Fields:

| Field | Value |
|-----|-----|
| Company | Dank Mushrooms, LLC |
| Status | Active |
| Department | Operations |
| Designation | Cultivation Technician |
| Default Shift | Day Shift |

Save.

---

# Enable Employee Portal Access

Open the employee **User account**.

Roles:

Employee

Remove:

System Manager
Accounts User
HR Manager

Employee can log in at:

https://erp.danks.store

---

# Enable Attendance Tracking

Create shift:

HR → Shift Type → New

Example:

| Field | Value |
|------|------|
| Shift Name | Day Shift |
| Start Time | 09:00 |
| End Time | 17:00 |
| Enable Auto Attendance | Yes |

Assign the shift to the employee.

Employee will use:

Check In
Check Out

---

# Payroll Setup

Create salary components.

Navigate:

Payroll → Salary Component

Create:

Earnings

Hourly Wage

Deductions

Federal Withholding
Colorado Withholding
Social Security
Medicare

---

## Create Salary Structure

Navigate:

Payroll → Salary Structure

Example:

Dank Mushrooms Hourly

Add components:

Earnings

Hourly Wage

Deductions

Federal Withholding
Colorado Withholding
Social Security
Medicare

Save.

---

## Assign Salary Structure

Navigate:

Payroll → Salary Structure Assignment

Assign structure to the employee.

---

## Weekly Payroll Workflow

Each week:

Payroll Entry
Get Employees
Create Salary Slips
Submit

Employee receives email payslip.

---

# Workspace Creation (ERPNext v16 Quirk) - Use Custom Page (below) instead

ERPNext currently **does not show the "New Workspace" button in the UI**.

Workspace must be created by manually entering the URL.

Open:

https://erp.danks.store/app/workspace/new-workspace-1

Create workspace:

| Field | Value |
|------|------|
| Title | Employee Dashboard |
| Module | HR |
| App | hrms |
| Type | Workspace |
| Icon | calendar |

Save.

If the workspace route fails initially, fix from backend.

---

## Fix Workspace From Backend

Open bench console:

docker compose exec erpnext-backend bench --site erp.danks.store console

Run:

doc = frappe.get_doc("Workspace", "employee-dashboard")
doc.route = "employee-dashboard"
doc.icon = "calendar"
doc.save(ignore_permissions=True)
frappe.db.commit()
frappe.clear_cache()

Then run:

bench --site erp.danks.store migrate
bench --site erp.danks.store clear-cache

---

## Workspace URL

Workspace will appear at:

https://erp.danks.store/app/employee-dashboard

---

## Configure Workspace

Open workspace.

Click **Edit**.

Add shortcuts:

| Label | Link |
|------|------|
| Check In / Check Out | Employee Checkin |
| My Attendance | Attendance |
| My Payslips | Salary Slip |
| Submit Expense | Expense Claim |

Save.

---

## Restrict Workspace to Employees

In workspace settings add role:

Employee

---

## Set Default Workspace for Employee

Open employee **User record**.

Under **Desk Settings**:

Default Workspace = Employee Dashboard

Now when the employee logs in they see only:

Check In / Check Out
My Attendance
My Payslips
Submit Expense

---


# RootedOps ERPNext Configuration Guide

This directory contains the initial configuration data and instructions for setting up ERPNext for:

- Dank Mushrooms, LLC
- Rooted Psyche

The goal of this configuration is to provide:

- basic accounting
- payroll tracking
- employee attendance
- vendor tracking
- project tracking
- asset tracking
- a simplified employee interface

---

# Directory Contents

| File | Purpose |
|-----|------|
| companies.csv | Creates Dank Mushrooms, LLC and Rooted Psyche companies |
| chart_of_accounts_dank_mushrooms_llc.csv | Dank Mushrooms Chart of Accounts |
| chart_of_accounts_rooted_psyche.csv | Rooted Psyche Chart of Accounts |
| cost_centers.csv | Cost centers used for payroll and accounting |
| departments.csv | Company departments |
| designations.csv | Employee job titles |
| employees_template.csv | Template for employee records |
| bank_accounts_template.csv | Business bank accounts |
| suppliers.csv | Vendors (Amazon, suppliers, etc.) |
| projects.csv | Projects such as farmers markets |
| expense_claim_types.csv | Expense categories |
| asset_categories.csv | Asset depreciation categories |
| RootedOps_ERPNext_Config_Pack.xlsx | Reference spreadsheet |

---

# Reset ERPNext to a Clean State (Optional)

If ERPNext already has data, wipe the site.

Stop ERPNext:

docker compose down

Remove ERPNext volumes:

docker volume rm docker_erpnext_db_data
docker volume rm docker_erpnext_sites
docker volume rm docker_erpnext_apps
docker volume rm docker_erpnext_logs

Restart ERPNext:

docker compose up -d

Run bootstrap again if necessary.

---

# Import Order (Important)

ERPNext imports must be done in the correct order.

Import using **Data Import Tool**.

Order:

1. companies.csv
2. Chart of Accounts (per company)
3. cost_centers.csv
4. departments.csv
5. designations.csv
6. bank_accounts_template.csv
7. suppliers.csv
8. projects.csv
9. expense_claim_types.csv
10. asset_categories.csv
11. employees_template.csv

---

# Create Employee

Navigate:

HR → Employee → New

Fields:

| Field | Value |
|-----|-----|
| Company | Dank Mushrooms, LLC |
| Status | Active |
| Department | Operations |
| Designation | Cultivation Technician |
| Default Shift | Day Shift |

Save.

---

# Enable Attendance Tracking

Create shift:

HR → Shift Type → New

Example:

| Field | Value |
|------|------|
| Shift Name | Day Shift |
| Start Time | 09:00 |
| End Time | 17:00 |
| Enable Auto Attendance | Yes |

Assign the shift to the employee.

Employee will use:

Check In
Check Out

---

# Payroll Setup

Create salary components.

Navigate:

Payroll → Salary Component

Create:

Earnings

Hourly Wage

Deductions

Federal Withholding
Colorado Withholding
Social Security
Medicare

---

## Weekly Payroll Workflow

Each week:

Payroll Entry
Get Employees
Create Salary Slips
Submit

Employee receives email payslip.

---

# Custom Employee Desk Page (Working Alternative to Workspace)

Due to instability in the ERPNext v16 Workspace UI and migration behavior that removes custom workspaces,
a custom Desk Page was created instead.

The page currently functions at:

https://erp.danks.store/desk/employee-home

or

https://erp.danks.store/app/employee-home

This provides a stable employee entry point while remaining inside ERPNext.

---

## Why This Was Needed

Workspace issues encountered:

- "New Workspace" button missing from UI
- Workspace creation required manual URL entry
- Workspace assets removed during migrate
- Workspace editor missing in this build
- Workspaces occasionally appeared blank

Desk Pages load directly from filesystem assets and are more reliable.

---

## Page Creation Process

From the backend console:

docker compose exec erpnext-backend bench --site erp.danks.store console

Python:

import frappe

if not frappe.db.exists("Page", "employee-home"):
    doc = frappe.get_doc({
        "doctype": "Page",
        "title": "Employee Home",
        "page_name": "employee-home",
        "module": "HR",
        "standard": "No"
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()

---

## Filesystem Assets

Path created inside container:

apps/hrms/hrms/hr/page/employee_home

Commands:

cd /home/frappe/frappe-bench/apps/hrms/hrms/hr/page
mkdir -p employee_home
touch employee_home/__init__.py

---

## employee_home.js

frappe.pages['employee-home'].on_page_load = function(wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'Employee Home',
        single_column: true
    });

    const html = `
        <div style="padding:16px;">
            <h3>Employee Home</h3>
            <div style="display:grid;gap:12px;max-width:420px;">
                <a class="btn btn-primary" href="/app/employee-checkin/new">Check In / Check Out</a>
                <a class="btn btn-default" href="/app/attendance">My Attendance</a>
                <a class="btn btn-default" href="/app/salary-slip">My Payslips</a>
                <a class="btn btn-default" href="/app/expense-claim">Submit Expense</a>
            </div>
        </div>
    `;

    $(page.body).append(html);
};

---

## Reload ERPNext

bench --site erp.danks.store clear-cache
bench --site erp.danks.store migrate

---

## Page Permissions

Navigate:

Settings → Role Permission for Page and Report

Add:

Role: Employee
Page: employee-home

---

## Optional Friendly URL

Example nginx rule:

location = /employee {
    return 302 https://erp.danks.store/app/employee-home;
}

Employees can then access:

https://erp.danks.store/employee

---

# Bank Accounts

Import:

bank_accounts_template.csv

Expected accounts:

Dank Mushrooms Checking
Dank Mushrooms Savings
Payroll Withholding
Rooted Psyche Bank Account

---

# Vendors

Import:

suppliers.csv

Examples:

Amazon
Myco Supply
Farmers Market Vendors
Advertising Vendors

---

# Projects

Projects allow tracking revenue sources.

Examples:

Farmers Market – Fort Collins
Farmers Market – Boulder
Online Sales

---

# Assets

Import:

asset_categories.csv

Example categories:

Cultivation Equipment
Market Equipment
Refrigeration
Processing Equipment

ERPNext will automatically track depreciation.

---

# Inter-Company Billing

Rooted Psyche will pay Dank Mushrooms for:

Cultivation services
Space rental
Property lease

Workflow:

Dank Mushrooms creates:

Sales Invoice

Rooted Psyche records:

Purchase Invoice

ERPNext links them automatically.

---

# Donations

Rooted Psyche income:

Donation Income

Expenses can be tracked normally.

---

# Weekly Operational Workflow

Employee:

Login
Check In
Work
Check Out

Owner:

Review attendance
Run payroll
Approve expenses
Review accounting

---

# Importing Clover and Ecwid Sales into ERPNext

Dank Mushrooms receives sales through:

- Clover (farmers market POS)
- Ecwid (online store)

These sales should be periodically recorded in ERPNext so accounting reports remain accurate.

Recommended workflow:

1. Export sales reports from Clover and Ecwid.
2. Summarize totals for the period (daily or weekly).
3. Record sales in ERPNext using Sales Invoice or Journal Entry.

Example accounts:

Sales → Website Sales
Sales → Farmers Market Sales

Cash payments:

Bank → Dank Mushrooms Checking

Workflow example:

Sales Invoice
Customer: Farmers Market Sales
Items: Market Products
Income Account: Farmers Market Sales
Payment Mode: Cash / Clover

For Ecwid:

Sales Invoice
Customer: Online Store
Income Account: Website Sales
Payment Mode: Stripe / Online Payment

Future improvement:

These platforms can eventually be integrated using:

- ERPNext API
- n8n automation
- scheduled CSV imports

Example architecture:

Ecwid / Clover → n8n → ERPNext API

This allows fully automated bookkeeping.

---

# Current Status

Working:

- custom ERPNext Desk Page
- employee check-in link
- attendance view
- payslip view
- expense claim link

Possible future improvements:

- check-in / check-out buttons
- today's attendance status
- weekly hours summary
- latest payslip display
- mobile-friendly layout

## Notes

ERPNext workspace creation is currently inconsistent in v16.

If workspace disappears after migration:

bench clear-cache
bench migrate

may remove orphan workspaces.

If that happens, recreate workspace using the manual URL again.



