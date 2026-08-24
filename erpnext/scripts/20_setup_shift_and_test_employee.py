"""RootedOps ERPNext shift + test employee helper.

Run inside bench console with:
    exec(open("/home/frappe/frappe-bench/sites/20_setup_shift_and_test_employee.py").read(), globals())
"""

import frappe

TEST_EMPLOYEE_EMAIL = "test.employee@example.com"
TEST_EMPLOYEE_NAME = "Test Employee"
TEST_EMPLOYEE_ID = "HR-EMP-00001"
TEST_COMPANY = "Dank Mushrooms, LLC"
TEST_DEPARTMENT = "Operations - DML"
TEST_DESIGNATION = "Cultivation Technician"
SHIFT_NAME = "Day Shift"

def ensure_payroll_settings():
    ps = frappe.get_single("Payroll Settings")
    ps.payroll_based_on = "Attendance"
    ps.consider_unmarked_attendance_as = "Absent"
    ps.email_salary_slip_to_employee = 1
    ps.save()
    return ps

def ensure_shift():
    name = frappe.db.exists("Shift Type", SHIFT_NAME)
    if name:
        doc = frappe.get_doc("Shift Type", name)
    else:
        doc = frappe.get_doc({
            "doctype": "Shift Type",
            "name": SHIFT_NAME,
            "start_time": "09:00:00",
            "end_time": "17:00:00",
        })
        doc.insert(ignore_permissions=True)

    doc.enable_auto_attendance = 1
    doc.determine_check_in_and_check_out = "Strictly based on Log Type in Employee Checkin"
    doc.working_hours_calculation_based_on = "Every Valid Check-in and Check-out"
    doc.begin_check_in_before_shift_start_time = 60
    doc.allow_check_out_after_shift_end_time = 60
    doc.process_attendance_after = "2026-03-14"
    doc.last_sync_of_checkin = "2026-03-17 23:59:59"
    doc.save()
    return doc

def ensure_user(email, full_name):
    if frappe.db.exists("User", email):
        return frappe.get_doc("User", email)
    doc = frappe.get_doc({
        "doctype": "User",
        "email": email,
        "first_name": full_name,
        "enabled": 1,
        "send_welcome_email": 0,
    })
    doc.insert(ignore_permissions=True)
    return doc

def ensure_employee(user_email):
    existing = frappe.db.exists("Employee", {"user_id": user_email})
    if existing:
        doc = frappe.get_doc("Employee", existing)
    else:
        doc = frappe.get_doc({
            "doctype": "Employee",
            "employee_name": TEST_EMPLOYEE_NAME,
            "company": TEST_COMPANY,
            "status": "Active",
            "department": TEST_DEPARTMENT,
            "designation": TEST_DESIGNATION,
            "user_id": user_email,
        })
        doc.insert(ignore_permissions=True)

    doc.default_shift = SHIFT_NAME
    doc.status = "Active"
    doc.save()
    return doc

def ensure_shift_assignment(employee_name):
    existing = frappe.db.exists("Shift Assignment", {"employee": employee_name, "shift_type": SHIFT_NAME, "start_date": "2026-03-01"})
    if existing:
        doc = frappe.get_doc("Shift Assignment", existing)
    else:
        doc = frappe.get_doc({
            "doctype": "Shift Assignment",
            "employee": employee_name,
            "shift_type": SHIFT_NAME,
            "start_date": "2026-03-01",
            "status": "Active",
        })
        doc.insert(ignore_permissions=True)

    if doc.docstatus == 0:
        doc.submit()
    return doc

ps = ensure_payroll_settings()
shift = ensure_shift()
user = ensure_user(TEST_EMPLOYEE_EMAIL, TEST_EMPLOYEE_NAME)
emp = ensure_employee(TEST_EMPLOYEE_EMAIL)
sa = ensure_shift_assignment(emp.name)

frappe.db.commit()
print({
    "payroll_settings": {"payroll_based_on": ps.payroll_based_on, "consider_unmarked_attendance_as": ps.consider_unmarked_attendance_as},
    "shift": shift.name,
    "employee": emp.name,
    "shift_assignment": sa.name,
})
