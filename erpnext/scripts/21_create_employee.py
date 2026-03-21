"""RootedOps ERPNext employee creation helper.

Purpose:
- create or update an employee suitable for payroll testing
- optionally create a linked User
- optionally create a submitted Shift Assignment
- optionally store hourly-payroll custom field values used by 50_hourly_payroll_automation.py

Run inside bench console with:
    exec(open("/home/frappe/frappe-bench/sites/21_create_employee.py").read(), globals())

Typical usage:
    result = create_or_update_employee(
        employee_name="Payroll Test Employee 2",
        first_name="Payroll",
        last_name="Employee 2",
        user_email="payroll.test2@example.com",
        company="Dank Mushrooms, LLC",
        department="Operations - DML",
        designation="Cultivation Technician",
        default_shift="Day Shift",
        shift_assignment_start_date="2026-03-01",
        hourly_rate=22.50,
        federal_profile={
            "filing_status": "Single",
            "step2_checked": 0,
            "step3_annual_credits": 0.0,
            "step4a_other_income": 0.0,
            "step4b_deductions": 0.0,
            "step4c_extra_withholding": 0.0,
            "exempt": 0,
        },
        colorado_profile={
            "filing_status": "Single",
            "dr0004_line2": None,
            "dr0004_line2_override": 0,
            "dr0004_line3": 0.0,
            "exempt": 0,
        },
    )
    result
"""

import frappe

DEFAULT_COMPANY = "Dank Mushrooms, LLC"
DEFAULT_DEPARTMENT = "Operations - DML"
DEFAULT_DESIGNATION = "Cultivation Technician"
DEFAULT_SHIFT = "Day Shift"
DEFAULT_SHIFT_ASSIGNMENT_START = "2026-03-01"

FEDERAL_FIELD_MAP = {
    "filing_status": "custom_federal_filing_status",
    "step2_checked": "custom_federal_step2_checked",
    "step3_annual_credits": "custom_federal_step3_annual_credits",
    "step4a_other_income": "custom_federal_step4a_other_income",
    "step4b_deductions": "custom_federal_step4b_deductions",
    "step4c_extra_withholding": "custom_federal_step4c_extra_withholding",
    "exempt": "custom_federal_tax_exempt",
}

COLORADO_FIELD_MAP = {
    "filing_status": "custom_colorado_filing_status",
    "dr0004_line2": "custom_colorado_dr0004_line2",
    "dr0004_line2_override": "custom_colorado_dr0004_line2_override",
    "dr0004_line3": "custom_colorado_dr0004_line3",
    "exempt": "custom_colorado_tax_exempt",
}

HOURLY_RATE_FIELDNAME = "custom_hourly_rate"


def _coerce_date(value):
    if not value:
        return None
    return frappe.utils.getdate(value)


def _default_date_of_birth(joining_date):
    joining_date = _coerce_date(joining_date) or frappe.utils.getdate()
    return frappe.utils.add_years(joining_date, -30)


def _pick_default_gender():
    meta = frappe.get_meta("Employee")
    field = meta.get_field("gender")
    options = []
    if field and getattr(field, "options", None):
        options = [opt.strip() for opt in field.options.split("\n") if opt.strip()]

    preferred = ["Male", "Female", "Other", "Prefer not to say"]
    for choice in preferred:
        if choice in options:
            return choice

    if options:
        return options[0]

    return "Other"


def _set_if_field_exists(doc, fieldname, value):
    if not fieldname:
        return False
    if fieldname not in doc.meta.get_fieldnames():
        return False
    doc.set(fieldname, value)
    return True


def ensure_user(user_email, first_name, last_name=None, enabled=1):
    if not user_email:
        return None

    full_name = " ".join([x for x in [first_name, last_name] if x]).strip() or user_email
    if frappe.db.exists("User", user_email):
        user = frappe.get_doc("User", user_email)
    else:
        user = frappe.get_doc({
            "doctype": "User",
            "email": user_email,
            "first_name": first_name or full_name,
            "last_name": last_name or "",
            "enabled": enabled,
            "send_welcome_email": 0,
        })
        user.insert(ignore_permissions=True)

    if user.first_name != (first_name or user.first_name):
        user.first_name = first_name or user.first_name
    if last_name is not None:
        user.last_name = last_name
    user.enabled = enabled
    user.save(ignore_permissions=True)
    return user


def ensure_employee(
    employee_name,
    first_name,
    last_name=None,
    user_email=None,
    company=DEFAULT_COMPANY,
    department=DEFAULT_DEPARTMENT,
    designation=DEFAULT_DESIGNATION,
    default_shift=DEFAULT_SHIFT,
    status="Active",
    gender=None,
    date_of_birth=None,
    date_of_joining=None,
):
    existing = None
    if user_email:
        existing = frappe.db.exists("Employee", {"user_id": user_email})
    if not existing and employee_name:
        existing = frappe.db.exists("Employee", {"employee_name": employee_name})

    resolved_joining_date = _coerce_date(date_of_joining)
    if not resolved_joining_date:
        resolved_joining_date = frappe.utils.getdate()

    resolved_date_of_birth = _coerce_date(date_of_birth) or _default_date_of_birth(resolved_joining_date)
    resolved_gender = gender or _pick_default_gender()

    if existing:
        emp = frappe.get_doc("Employee", existing)
    else:
        emp = frappe.get_doc({
            "doctype": "Employee",
            "employee_name": employee_name,
            "first_name": first_name or employee_name,
            "last_name": last_name or "",
            "company": company,
            "status": status,
            "department": department,
            "designation": designation,
            "user_id": user_email,
            "gender": resolved_gender,
            "date_of_birth": resolved_date_of_birth,
            "date_of_joining": resolved_joining_date,
        })
        emp.insert(ignore_permissions=True)

    emp.employee_name = employee_name or emp.employee_name
    if "first_name" in emp.meta.get_fieldnames():
        emp.first_name = first_name or emp.first_name
    if "last_name" in emp.meta.get_fieldnames() and last_name is not None:
        emp.last_name = last_name
    emp.company = company
    emp.department = department
    emp.designation = designation
    emp.status = status
    if user_email:
        emp.user_id = user_email
    if default_shift:
        emp.default_shift = default_shift
    if "gender" in emp.meta.get_fieldnames() and not getattr(emp, "gender", None):
        emp.gender = resolved_gender
    if "date_of_birth" in emp.meta.get_fieldnames() and not getattr(emp, "date_of_birth", None):
        emp.date_of_birth = resolved_date_of_birth
    if "date_of_joining" in emp.meta.get_fieldnames() and not getattr(emp, "date_of_joining", None):
        emp.date_of_joining = resolved_joining_date
    emp.save(ignore_permissions=True)
    return emp


def ensure_shift_assignment(employee_id, shift_type=DEFAULT_SHIFT, start_date=DEFAULT_SHIFT_ASSIGNMENT_START):
    if not shift_type or not start_date:
        return None

    existing = frappe.db.exists(
        "Shift Assignment",
        {"employee": employee_id, "shift_type": shift_type, "start_date": start_date},
    )
    if existing:
        doc = frappe.get_doc("Shift Assignment", existing)
    else:
        doc = frappe.get_doc({
            "doctype": "Shift Assignment",
            "employee": employee_id,
            "shift_type": shift_type,
            "start_date": start_date,
            "status": "Active",
        })
        doc.insert(ignore_permissions=True)

    doc.status = "Active"
    doc.save(ignore_permissions=True)
    if doc.docstatus == 0:
        doc.submit()
    return doc


def apply_payroll_profile(emp, hourly_rate=None, federal_profile=None, colorado_profile=None):
    updated_fields = []
    if hourly_rate is not None and _set_if_field_exists(emp, HOURLY_RATE_FIELDNAME, hourly_rate):
        updated_fields.append(HOURLY_RATE_FIELDNAME)

    for source, field_map in [
        (federal_profile or {}, FEDERAL_FIELD_MAP),
        (colorado_profile or {}, COLORADO_FIELD_MAP),
    ]:
        for key, value in source.items():
            fieldname = field_map.get(key)
            if _set_if_field_exists(emp, fieldname, value):
                updated_fields.append(fieldname)

    if updated_fields:
        emp.save(ignore_permissions=True)

    return sorted(set(updated_fields))


def create_or_update_employee(
    employee_name,
    first_name,
    last_name=None,
    user_email=None,
    company=DEFAULT_COMPANY,
    department=DEFAULT_DEPARTMENT,
    designation=DEFAULT_DESIGNATION,
    default_shift=DEFAULT_SHIFT,
    shift_assignment_start_date=DEFAULT_SHIFT_ASSIGNMENT_START,
    create_user_record=True,
    create_shift_assignment=True,
    hourly_rate=None,
    federal_profile=None,
    colorado_profile=None,
    gender=None,
    date_of_birth=None,
    date_of_joining=None,
):
    user = None
    if create_user_record and user_email:
        user = ensure_user(user_email=user_email, first_name=first_name, last_name=last_name)

    emp = ensure_employee(
        employee_name=employee_name,
        first_name=first_name,
        last_name=last_name,
        user_email=user_email,
        company=company,
        department=department,
        designation=designation,
        default_shift=default_shift,
        gender=gender,
        date_of_birth=date_of_birth,
        date_of_joining=date_of_joining or shift_assignment_start_date,
    )

    updated_payroll_fields = apply_payroll_profile(
        emp,
        hourly_rate=hourly_rate,
        federal_profile=federal_profile,
        colorado_profile=colorado_profile,
    )

    shift_assignment = None
    if create_shift_assignment and default_shift and shift_assignment_start_date:
        shift_assignment = ensure_shift_assignment(
            employee_id=emp.name,
            shift_type=default_shift,
            start_date=shift_assignment_start_date,
        )

    frappe.db.commit()

    return {
        "user": user.name if user else None,
        "employee": emp.name,
        "employee_name": emp.employee_name,
        "company": emp.company,
        "department": emp.department,
        "designation": emp.designation,
        "default_shift": getattr(emp, "default_shift", None),
        "shift_assignment": shift_assignment.name if shift_assignment else None,
        "payroll_fields_updated": updated_payroll_fields,
    }
