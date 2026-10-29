"""RootedOps ERPNext payroll test foundation helper.

Creates the clean salary structure and assignment used during hourly payroll testing.
Run inside bench console with:
    exec(open("/home/frappe/frappe-bench/sites/40_setup_payroll_test_foundation.py").read(), globals())
"""

import frappe

TEST_EMPLOYEE = "HR-EMP-00001"
TEST_COMPANY = "Dank Mushrooms, LLC"
TEST_STRUCTURE = "Dank Mushrooms Weekly Test"

def ensure_salary_structure():
    if frappe.db.exists("Salary Structure", TEST_STRUCTURE):
        doc = frappe.get_doc("Salary Structure", TEST_STRUCTURE)
        if doc.docstatus == 0:
            doc.submit()
        return doc

    doc = frappe.get_doc({
        "doctype": "Salary Structure",
        "name": TEST_STRUCTURE,
        "company": TEST_COMPANY,
        "is_active": "Yes",
        "currency": "USD",
        "payroll_frequency": "Weekly",
        "salary_slip_based_on_timesheet": 0,
        "earnings": [
            {
                "salary_component": "Hourly Wage",
                "amount": 800.0,
                "depends_on_payment_days": 1
            }
        ],
        "deductions": []
    })
    doc.insert(ignore_permissions=True)
    doc.submit()
    return doc

def delete_bad_assignment():
    bad = frappe.db.exists("Salary Structure Assignment", "HR-SSA-26-03-00002")
    if bad:
        doc = frappe.get_doc("Salary Structure Assignment", bad)
        if doc.docstatus == 1:
            doc.cancel()
        frappe.delete_doc("Salary Structure Assignment", doc.name, force=True)

def ensure_assignment():
    existing = frappe.db.exists("Salary Structure Assignment", {
        "employee": TEST_EMPLOYEE,
        "salary_structure": TEST_STRUCTURE,
        "from_date": "2026-03-15"
    })
    if existing:
        doc = frappe.get_doc("Salary Structure Assignment", existing)
        if doc.docstatus == 0:
            doc.submit()
        return doc

    doc = frappe.get_doc({
        "doctype": "Salary Structure Assignment",
        "employee": TEST_EMPLOYEE,
        "salary_structure": TEST_STRUCTURE,
        "from_date": "2026-03-15",
        "company": TEST_COMPANY,
        "base": 800.0,
        "currency": "USD",
        "payroll_payable_account": "Accounts Payable - DML",
        "payroll_cost_centers": [
            {"cost_center": "Dank Mushrooms Payroll - DML", "percentage": 100}
        ]
    })
    doc.insert(ignore_permissions=True)
    doc.submit()
    return doc

ss = ensure_salary_structure()
delete_bad_assignment()
ssa = ensure_assignment()
frappe.db.commit()
print({"salary_structure": ss.name, "assignment": ssa.name})
