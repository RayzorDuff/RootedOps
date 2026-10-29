"""RootedOps ERPNext employee creation helper.

Purpose:
- create or update an employee suitable for payroll testing
- optionally create a linked User
- optionally create a submitted Shift Assignment
- optionally store hourly-payroll custom field values used by 50_hourly_payroll_automation.py
- optionally create a submitted Salary Structure Assignment so the employee is payroll-ready
- backfill payroll setup for employees created before this helper was patched
- create test Employee Checkin IN/OUT pairs with auto-attendance enabled

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
        salary_structure="Dank Mushrooms Weekly Test",
        salary_structure_assignment_start_date="2026-03-15",
        salary_structure_base=800.0,
        create_salary_structure_assignment=True,
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
from frappe.utils import cint

DEFAULT_COMPANY = "Dank Mushrooms, LLC"
DEFAULT_DEPARTMENT = "Operations - DML"
DEFAULT_DESIGNATION = "Cultivation Technician"
DEFAULT_SHIFT = "Day Shift"
DEFAULT_SHIFT_ASSIGNMENT_START = "2026-03-01"

FEDERAL_FIELD_MAP = {
    "filing_status": "rootedops_federal_filing_status",
    "step2_checked": "rootedops_federal_step2_checked",
    "step3_annual_credits": "rootedops_federal_step3_annual_credits",
    "step4a_other_income": "rootedops_federal_step4a_other_income",
    "step4b_deductions": "rootedops_federal_step4b_deductions",
    "step4c_extra_withholding": "rootedops_federal_step4c_extra_withholding",
    "exempt": "rootedops_federal_exempt",
}

COLORADO_FIELD_MAP = {
    "filing_status": "rootedops_colorado_filing_status",
    "dr0004_line2": "rootedops_colorado_dr0004_line2",
    "dr0004_line2_override": "rootedops_colorado_dr0004_line2_override",
    "dr0004_line3": "rootedops_colorado_dr0004_line3",
    "exempt": "rootedops_colorado_exempt",
}

HOURLY_RATE_FIELDNAME = "rootedops_hourly_rate"
PAY_MODEL_FIELDNAME = "rootedops_pay_model"
OVERNIGHT_FLAT_AMOUNT_FIELDNAME = "rootedops_overnight_flat_amount"


def insert_checkin_pair(employee, in_time, out_time, skip_auto_attendance=0):
    """Create one IN/OUT Employee Checkin pair for testing payroll attendance.

    The saved rows are explicitly reloaded and saved so skip_auto_attendance is
    persisted as 0 in sites where initial insert defaults it to 1.
    """
    created = []
    for log_type, timestamp in (("IN", in_time), ("OUT", out_time)):
        doc = frappe.get_doc({
            "doctype": "Employee Checkin",
            "employee": employee,
            "time": timestamp,
            "log_type": log_type,
            "skip_auto_attendance": cint(skip_auto_attendance or 0),
        })
        doc.insert(ignore_permissions=True)
        doc.reload()
        doc.skip_auto_attendance = cint(skip_auto_attendance or 0)
        doc.save(ignore_permissions=True)
        created.append(doc.name)

    frappe.db.commit()
    return {"in": created[0], "out": created[1]}


def backfill_employee_payroll_setup(
    employee,
    hourly_rate=None,
    federal_profile=None,
    colorado_profile=None,
    pay_model=None,
    overnight_flat_amount=None,
    salary_structure=None,
    salary_structure_assignment_start_date=None,
    salary_structure_base=0.0,
    create_salary_structure_assignment=False,
    company=DEFAULT_COMPANY,
):
    """Repair payroll setup for an already-existing employee."""
    emp = frappe.get_doc("Employee", employee)
    updated_payroll_fields = apply_payroll_profile(
        emp,
        hourly_rate=hourly_rate,
        federal_profile=federal_profile,
        colorado_profile=colorado_profile,
        pay_model=pay_model,
        overnight_flat_amount=overnight_flat_amount,
    )

    salary_structure_assignment = None
    if create_salary_structure_assignment and salary_structure:
        salary_structure_assignment = ensure_salary_structure_assignment(
            employee_id=emp.name,
            salary_structure=salary_structure,
            from_date=salary_structure_assignment_start_date,
            company=company or emp.company,
            base=salary_structure_base,
        )

    frappe.db.commit()
    return {
        "employee": emp.name,
        "employee_name": emp.employee_name,
        "salary_structure_assignment": salary_structure_assignment.name if salary_structure_assignment else None,
        "salary_structure": salary_structure_assignment.salary_structure if salary_structure_assignment else None,
        "payroll_fields_updated": updated_payroll_fields,
    }


def _coerce_date(value):
    if not value:
        return None
    return frappe.utils.getdate(value)


def _default_date_of_birth(joining_date):
    joining_date = _coerce_date(joining_date) or frappe.utils.getdate()
    return frappe.utils.add_years(joining_date, -30)


def _meta_has_field(doc_or_meta, fieldname):
    if not fieldname:
        return False

    meta = getattr(doc_or_meta, "meta", doc_or_meta)
    return bool(meta and meta.get_field(fieldname))


def _resolve_gender_value(preferred=None):
    meta = frappe.get_meta("Employee")
    field = meta.get_field("gender")
    if not field:
        return preferred or None

    preferred_values = []
    for value in [preferred, "Male", "Female", "Other", "Prefer not to say"]:
        if value and value not in preferred_values:
            preferred_values.append(value)

    if field.fieldtype == "Select":
        options = [opt.strip() for opt in (field.options or "").split("\n") if opt.strip()]
        for choice in preferred_values:
            if choice in options:
                return choice
        return options[0] if options else (preferred or None)

    if field.fieldtype == "Link":
        options_doctype = field.options
        if not options_doctype:
            return preferred or None

        for choice in preferred_values:
            if frappe.db.exists(options_doctype, choice):
                return choice

        existing = frappe.get_all(options_doctype, pluck="name", limit=1)
        if existing:
            return existing[0]

        if options_doctype == "Gender":
            for choice in preferred_values:
                try:
                    doc = frappe.get_doc({
                        "doctype": "Gender",
                        "gender": choice,
                    })
                    doc.insert(ignore_permissions=True)
                    return doc.name
                except Exception:
                    frappe.db.rollback()
                    continue

    return preferred or None


def _set_if_field_exists(doc, fieldname, value):
    if not fieldname:
        return False
    if not _meta_has_field(doc, fieldname):
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
    resolved_gender = _resolve_gender_value(gender)

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
    if _meta_has_field(emp, "first_name"):
        emp.first_name = first_name or emp.first_name
    if _meta_has_field(emp, "last_name") and last_name is not None:
        emp.last_name = last_name
    emp.company = company
    emp.department = department
    emp.designation = designation
    emp.status = status
    if user_email:
        emp.user_id = user_email
    if default_shift and _meta_has_field(emp, "default_shift"):
        emp.default_shift = default_shift
    if _meta_has_field(emp, "gender") and resolved_gender and not getattr(emp, "gender", None):
        emp.gender = resolved_gender
    if _meta_has_field(emp, "date_of_birth") and not getattr(emp, "date_of_birth", None):
        emp.date_of_birth = resolved_date_of_birth
    if _meta_has_field(emp, "date_of_joining") and not getattr(emp, "date_of_joining", None):
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


def ensure_salary_structure_assignment(
    employee_id,
    salary_structure=None,
    from_date=None,
    company=DEFAULT_COMPANY,
    base=0.0,
):
    if not salary_structure or not from_date:
        return None

    existing = frappe.db.exists(
        "Salary Structure Assignment",
        {
            "employee": employee_id,
            "salary_structure": salary_structure,
            "from_date": from_date,
            "docstatus": ["<", 2],
        },
    )
    if existing:
        doc = frappe.get_doc("Salary Structure Assignment", existing)
    else:
        doc = frappe.get_doc({
            "doctype": "Salary Structure Assignment",
            "employee": employee_id,
            "salary_structure": salary_structure,
            "from_date": from_date,
            "company": company,
            "base": base,
        })
        doc.insert(ignore_permissions=True)

    doc.company = company
    doc.base = frappe.utils.flt(base or 0.0, 2)
    doc.save(ignore_permissions=True)
    if doc.docstatus == 0:
        doc.submit()
    return doc


def apply_payroll_profile(
    emp,
    hourly_rate=None,
    federal_profile=None,
    colorado_profile=None,
    pay_model=None,
    overnight_flat_amount=None,
):
    updated_fields = []
    if hourly_rate is not None and _set_if_field_exists(emp, HOURLY_RATE_FIELDNAME, hourly_rate):
        updated_fields.append(HOURLY_RATE_FIELDNAME)
    if pay_model is not None and _set_if_field_exists(emp, PAY_MODEL_FIELDNAME, pay_model):
        updated_fields.append(PAY_MODEL_FIELDNAME)
    if overnight_flat_amount is not None and _set_if_field_exists(emp, OVERNIGHT_FLAT_AMOUNT_FIELDNAME, overnight_flat_amount):
        updated_fields.append(OVERNIGHT_FLAT_AMOUNT_FIELDNAME)

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
    pay_model=None,
    overnight_flat_amount=None,
    gender=None,
    date_of_birth=None,
    date_of_joining=None,
    salary_structure=None,
    salary_structure_assignment_start_date=None,
    salary_structure_base=0.0,
    create_salary_structure_assignment=False,
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
        pay_model=pay_model,
        overnight_flat_amount=overnight_flat_amount,
    )

    shift_assignment = None
    if create_shift_assignment and default_shift and shift_assignment_start_date:
        shift_assignment = ensure_shift_assignment(
            employee_id=emp.name,
            shift_type=default_shift,
            start_date=shift_assignment_start_date,
        )

    salary_structure_assignment = None
    if create_salary_structure_assignment and salary_structure:
        salary_structure_assignment = ensure_salary_structure_assignment(
            employee_id=emp.name,
            salary_structure=salary_structure,
            from_date=salary_structure_assignment_start_date or shift_assignment_start_date or date_of_joining,
            company=company,
            base=salary_structure_base,
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
        "salary_structure_assignment": salary_structure_assignment.name if salary_structure_assignment else None,
        "salary_structure": salary_structure_assignment.salary_structure if salary_structure_assignment else None,
        "payroll_fields_updated": updated_payroll_fields,
    }
