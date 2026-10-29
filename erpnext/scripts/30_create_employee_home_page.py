"""RootedOps ERPNext employee home Desk page helper.

This script writes the page assets into the hrms app path used by the running container.

Run inside bench console with:
    exec(open("/home/frappe/frappe-bench/sites/30_create_employee_home_page.py").read(), globals())
"""

import frappe
from pathlib import Path

PAGE_DIR = Path("/home/frappe/frappe-bench/apps/hrms/hrms/hr/page/employee_home")
PAGE_DIR.mkdir(parents=True, exist_ok=True)

(PAGE_DIR / "__init__.py").write_text("", encoding="utf-8")

(PAGE_DIR / "employee_home.js").write_text(
    """frappe.pages['employee-home'].on_page_load = function(wrapper) {
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
};""",
    encoding="utf-8"
)

(PAGE_DIR / "employee_home.json").write_text(
    """{
 "doctype": "Page",
 "module": "HR",
 "name": "employee-home",
 "page_name": "employee-home",
 "title": "Employee Home",
 "standard": "Yes"
}
""",
    encoding="utf-8"
)

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
print({"page_dir": str(PAGE_DIR), "page": "employee-home"})
