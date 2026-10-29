"""RootedOps ERPNext master-data helper.

Run inside bench console with:
    exec(open("/home/frappe/frappe-bench/sites/10_setup_master_data.py").read(), globals())

This script creates or updates the basic payroll-facing structures that were
previously handled only by CSV imports and ad-hoc console work.
"""

import frappe

COMPANIES = ["Dank Mushrooms, LLC", "Rooted Psyche"]

DEPARTMENTS = [
    ("Dank Mushrooms, LLC", "Operations"),
    ("Dank Mushrooms, LLC", "Administration"),
    ("Rooted Psyche", "Administration"),
    ("Rooted Psyche", "Facilitation"),
]

DESIGNATIONS = [
    "Cultivation Technician",
    "Operations Assistant",
    "Facilitator",
    "Administrator",
]

COST_CENTERS = [
    ("Dank Mushrooms, LLC", "Dank Mushrooms Payroll"),
    ("Dank Mushrooms, LLC", "Dank Mushrooms Operations"),
    ("Rooted Psyche", "Rooted Psyche Administration"),
]

def ensure_department(company, department_name):
    existing = frappe.db.exists("Department", {"department_name": department_name, "company": company})
    if existing:
        return existing
    doc = frappe.get_doc({
        "doctype": "Department",
        "department_name": department_name,
        "company": company,
    })
    doc.insert(ignore_permissions=True)
    return doc.name

def ensure_designation(name):
    existing = frappe.db.exists("Designation", {"designation_name": name})
    if existing:
        return existing
    doc = frappe.get_doc({
        "doctype": "Designation",
        "designation_name": name,
    })
    doc.insert(ignore_permissions=True)
    return doc.name

def ensure_cost_center(company, cost_center_name):
    existing = frappe.db.exists("Cost Center", {"cost_center_name": cost_center_name, "company": company})
    if existing:
        return existing
    doc = frappe.get_doc({
        "doctype": "Cost Center",
        "cost_center_name": cost_center_name,
        "company": company,
        "is_group": 0,
    })
    doc.insert(ignore_permissions=True)
    return doc.name

created = {"departments": [], "designations": [], "cost_centers": []}

for company, dept in DEPARTMENTS:
    created["departments"].append(ensure_department(company, dept))

for desig in DESIGNATIONS:
    created["designations"].append(ensure_designation(desig))

for company, cc in COST_CENTERS:
    created["cost_centers"].append(ensure_cost_center(company, cc))

frappe.db.commit()
print(created)
