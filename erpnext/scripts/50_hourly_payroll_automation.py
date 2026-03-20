"""RootedOps ERPNext hourly payroll automation.

Phase 3 scope currently implemented:
- Attendance-based hourly payroll
- Gross pay from submitted Attendance working hours
- Employee Social Security
- Employee Medicare
- Employer Social Security (reported in return value)
- Employer Medicare (reported in return value)

Not yet implemented:
- Federal withholding from W-4 / IRS 15-T
- Colorado withholding from state inputs
- Payroll Entry / Journal Entry automation
- Employer tax posting automation

IMPORTANT:
This script intentionally builds a CUSTOM salary slip path and does NOT rely on
ERPNext Salary Structure earnings math. That avoids payment-day proration from
the test Salary Structure assignment, which was causing gross/net mismatch.

Run inside bench console with:
    exec(open("/home/frappe/frappe-bench/sites/50_hourly_payroll_automation.py").read(), globals())
"""

import frappe
from frappe.utils import flt, getdate, date_diff

SS_WAGE_BASE_2026 = 184500.0
SS_RATE = 0.062
MEDICARE_RATE = 0.0145


def get_present_attendance_rows(employee, start_date, end_date):
    return frappe.get_all(
        "Attendance",
        filters={
            "employee": employee,
            "attendance_date": ["between", [start_date, end_date]],
            "docstatus": 1,
            "status": "Present",
        },
        fields=["name", "attendance_date", "working_hours"],
        order_by="attendance_date asc",
    )


def attendance_summary(employee, start_date, end_date):
    rows = get_present_attendance_rows(employee, start_date, end_date)
    total_hours = sum(flt(row.working_hours) for row in rows)
    payment_days = len({str(row.attendance_date) for row in rows})
    total_working_days = date_diff(getdate(end_date), getdate(start_date)) + 1
    absent_days = max(0, total_working_days - payment_days)

    return {
        "rows": rows,
        "hours": flt(total_hours, 2),
        "payment_days": flt(payment_days, 2),
        "total_working_days": flt(total_working_days, 2),
        "absent_days": flt(absent_days, 2),
    }


def ytd_gross_before_period(employee, start_date, exclude_slip_name=None):
    filters = {
        "employee": employee,
        "docstatus": ["<", 2],
        "end_date": ["<", start_date],
    }
    rows = frappe.get_all("Salary Slip", filters=filters, fields=["name", "gross_pay"])

    total = 0.0
    for row in rows:
        if exclude_slip_name and row.name == exclude_slip_name:
            continue
        total += flt(row.gross_pay)

    return flt(total, 2)


def ss_employee_amount(current_gross, ytd_before):
    taxable_remaining = max(0.0, SS_WAGE_BASE_2026 - flt(ytd_before))
    taxable_now = min(flt(current_gross), taxable_remaining)
    return flt(taxable_now * SS_RATE, 2)


def medicare_employee_amount(current_gross):
    return flt(flt(current_gross) * MEDICARE_RATE, 2)


def ss_employer_amount(current_gross, ytd_before):
    taxable_remaining = max(0.0, SS_WAGE_BASE_2026 - flt(ytd_before))
    taxable_now = min(flt(current_gross), taxable_remaining)
    return flt(taxable_now * SS_RATE, 2)


def medicare_employer_amount(current_gross):
    return flt(flt(current_gross) * MEDICARE_RATE, 2)


def get_employee_doc(employee):
    return frappe.get_doc("Employee", employee)


def get_employee_payroll_context(employee, company=None):
    emp = get_employee_doc(employee)

    resolved_company = company or emp.company
    payroll_payable_account = None
    cost_center = None

    if getattr(emp, "payroll_cost_center", None):
        cost_center = emp.payroll_cost_center

    if not cost_center and getattr(emp, "department", None):
        department = frappe.db.get_value(
            "Department",
            emp.department,
            ["payroll_cost_center"],
            as_dict=True,
        )
        if department and department.payroll_cost_center:
            cost_center = department.payroll_cost_center

    if not payroll_payable_account:
        company_doc = frappe.get_doc("Company", resolved_company)
        payroll_payable_account = getattr(company_doc, "default_payroll_payable_account", None)

    return {
        "employee_doc": emp,
        "company": resolved_company,
        "currency": getattr(emp, "salary_currency", None) or "USD",
        "payroll_payable_account": payroll_payable_account,
        "cost_center": cost_center,
    }


def get_existing_draft_slip(employee, start_date, end_date):
    slips = frappe.get_all(
        "Salary Slip",
        filters={
            "employee": employee,
            "start_date": start_date,
            "end_date": end_date,
            "docstatus": 0,
        },
        pluck="name",
        order_by="creation desc",
    )
    return slips[0] if slips else None


def get_existing_submitted_slip(employee, start_date, end_date):
    slips = frappe.get_all(
        "Salary Slip",
        filters={
            "employee": employee,
            "start_date": start_date,
            "end_date": end_date,
            "docstatus": 1,
        },
        pluck="name",
        order_by="creation desc",
    )
    return slips[0] if slips else None


def ensure_draft_salary_slip(employee, start_date, end_date, payroll_frequency="Weekly", company=None):
    submitted = get_existing_submitted_slip(employee, start_date, end_date)
    if submitted:
        frappe.throw(
            f"Submitted Salary Slip already exists for {employee} {start_date} to {end_date}: {submitted}"
        )

    existing = get_existing_draft_slip(employee, start_date, end_date)
    if existing:
        return frappe.get_doc("Salary Slip", existing)

    payroll_context = get_employee_payroll_context(employee, company=company)

    slip = frappe.get_doc(
        {
            "doctype": "Salary Slip",
            "employee": employee,
            "company": payroll_context["company"],
            "start_date": start_date,
            "end_date": end_date,
            "payroll_frequency": payroll_frequency,
            "currency": payroll_context["currency"],
        }
    )
    slip.insert(ignore_permissions=True)
    return slip


def clear_structure_fields(slip):
    # Prevent ERPNext from pulling salary-structure math back onto this custom slip.
    if hasattr(slip, "salary_structure"):
        slip.salary_structure = None
    if hasattr(slip, "salary_slip_based_on_timesheet"):
        slip.salary_slip_based_on_timesheet = 0
    if hasattr(slip, "timesheets"):
        slip.set("timesheets", [])
    return slip


def set_context_fields_on_slip(slip, employee, start_date, end_date, payroll_frequency, company=None):
    payroll_context = get_employee_payroll_context(employee, company=company)
    summary = attendance_summary(employee, start_date, end_date)

    slip.employee = employee
    slip.company = payroll_context["company"]
    slip.start_date = start_date
    slip.end_date = end_date
    slip.payroll_frequency = payroll_frequency
    slip.currency = payroll_context["currency"]

    if payroll_context["payroll_payable_account"] and hasattr(slip, "payroll_payable_account"):
        slip.payroll_payable_account = payroll_context["payroll_payable_account"]

    if payroll_context["cost_center"] and hasattr(slip, "cost_center"):
        slip.cost_center = payroll_context["cost_center"]

    if hasattr(slip, "payment_days"):
        slip.payment_days = summary["payment_days"]
    if hasattr(slip, "total_working_days"):
        slip.total_working_days = summary["total_working_days"]
    if hasattr(slip, "leave_without_pay"):
        slip.leave_without_pay = 0
    if hasattr(slip, "absent_days"):
        slip.absent_days = summary["absent_days"]
    if hasattr(slip, "total_working_hours"):
        slip.total_working_hours = summary["hours"]

    return payroll_context, summary


def replace_child_table(doc, table_fieldname, rows):
    doc.set(table_fieldname, [])
    for row in rows:
        doc.append(table_fieldname, row)


def build_earnings_rows(gross):
    return [
        {
            "salary_component": "Hourly Wage",
            "abbr": "HOUR",
            "amount": flt(gross, 2),
            "default_amount": flt(gross, 2),
            "depends_on_payment_days": 0,
        }
    ]


def build_deduction_rows(ss_employee, medicare_employee, federal_withholding=0.0, colorado_withholding=0.0):
    rows = [
        {
            "salary_component": "Social Security",
            "abbr": "SS",
            "amount": flt(ss_employee, 2),
            "default_amount": flt(ss_employee, 2),
            "depends_on_payment_days": 0,
        },
        {
            "salary_component": "Medicare",
            "abbr": "MED",
            "amount": flt(medicare_employee, 2),
            "default_amount": flt(medicare_employee, 2),
            "depends_on_payment_days": 0,
        },
    ]

    if flt(federal_withholding):
        rows.append(
            {
                "salary_component": "Federal Withholding",
                "abbr": "FEDWH",
                "amount": flt(federal_withholding, 2),
                "default_amount": flt(federal_withholding, 2),
                "depends_on_payment_days": 0,
            }
        )

    if flt(colorado_withholding):
        rows.append(
            {
                "salary_component": "Colorado Withholding",
                "abbr": "COWH",
                "amount": flt(colorado_withholding, 2),
                "default_amount": flt(colorado_withholding, 2),
                "depends_on_payment_days": 0,
            }
        )

    return rows


def set_manual_totals(slip):
    earnings_sum = flt(sum(flt(row.amount) for row in slip.earnings), 2)
    deductions_sum = flt(sum(flt(row.amount) for row in slip.deductions), 2)
    net_pay = flt(earnings_sum - deductions_sum, 2)

    if hasattr(slip, "gross_pay"):
        slip.gross_pay = earnings_sum
    if hasattr(slip, "total_deduction"):
        slip.total_deduction = deductions_sum
    if hasattr(slip, "net_pay"):
        slip.net_pay = net_pay
    if hasattr(slip, "rounded_total"):
        slip.rounded_total = net_pay

    return {
        "gross_pay": earnings_sum,
        "total_deduction": deductions_sum,
        "net_pay": net_pay,
    }


def validate_custom_math(slip, expected_gross, expected_net):
    actual_gross = flt(getattr(slip, "gross_pay", 0.0), 2)
    actual_net = flt(getattr(slip, "net_pay", 0.0), 2)

    issues = []
    if actual_gross != flt(expected_gross, 2):
        issues.append(f"gross_pay expected {flt(expected_gross, 2)} but got {actual_gross}")
    if actual_net != flt(expected_net, 2):
        issues.append(f"net_pay expected {flt(expected_net, 2)} but got {actual_net}")

    return issues


def diagnose_salary_slip_math(slip_name):
    slip = frappe.get_doc("Salary Slip", slip_name)

    earnings = [
        {
            "salary_component": row.salary_component,
            "amount": flt(row.amount, 2),
            "default_amount": flt(getattr(row, "default_amount", 0.0), 2),
            "depends_on_payment_days": int(flt(getattr(row, "depends_on_payment_days", 0))),
        }
        for row in slip.earnings
    ]

    deductions = [
        {
            "salary_component": row.salary_component,
            "amount": flt(row.amount, 2),
            "default_amount": flt(getattr(row, "default_amount", 0.0), 2),
            "depends_on_payment_days": int(flt(getattr(row, "depends_on_payment_days", 0))),
        }
        for row in slip.deductions
    ]

    return {
        "slip_name": slip.name,
        "salary_structure": getattr(slip, "salary_structure", None),
        "payment_days": flt(getattr(slip, "payment_days", 0.0), 2),
        "total_working_days": flt(getattr(slip, "total_working_days", 0.0), 2),
        "gross_pay_field": flt(getattr(slip, "gross_pay", 0.0), 2),
        "total_deduction_field": flt(getattr(slip, "total_deduction", 0.0), 2),
        "net_pay_field": flt(getattr(slip, "net_pay", 0.0), 2),
        "earnings_sum": flt(sum(flt(row.amount) for row in slip.earnings), 2),
        "deductions_sum": flt(sum(flt(row.amount) for row in slip.deductions), 2),
        "earnings": earnings,
        "deductions": deductions,
    }


def rebuild_hourly_salary_slip(
    employee,
    start_date,
    end_date,
    hourly_rate,
    payroll_frequency="Weekly",
    company=None,
    federal_withholding=None,
    colorado_withholding=None,
):
    if federal_withholding is None:
        federal_withholding = 0.0
    if colorado_withholding is None:
        colorado_withholding = 0.0

    slip = ensure_draft_salary_slip(
        employee=employee,
        start_date=start_date,
        end_date=end_date,
        payroll_frequency=payroll_frequency,
        company=company,
    )

    payroll_context, summary = set_context_fields_on_slip(
        slip=slip,
        employee=employee,
        start_date=start_date,
        end_date=end_date,
        payroll_frequency=payroll_frequency,
        company=company,
    )

    clear_structure_fields(slip)

    gross = flt(summary["hours"] * flt(hourly_rate), 2)
    ytd_before = ytd_gross_before_period(employee, start_date, exclude_slip_name=slip.name)

    ss_employee = ss_employee_amount(gross, ytd_before)
    medicare_employee = medicare_employee_amount(gross)
    ss_employer = ss_employer_amount(gross, ytd_before)
    medicare_employer = medicare_employer_amount(gross)

    earnings_rows = build_earnings_rows(gross)
    deduction_rows = build_deduction_rows(
        ss_employee=ss_employee,
        medicare_employee=medicare_employee,
        federal_withholding=federal_withholding,
        colorado_withholding=colorado_withholding,
    )

    replace_child_table(slip, "earnings", earnings_rows)
    replace_child_table(slip, "deductions", deduction_rows)

    manual_totals = set_manual_totals(slip)

    slip.flags.ignore_validate_update_after_submit = True
    slip.save(ignore_permissions=True)
    slip.reload()

    issues = validate_custom_math(
        slip=slip,
        expected_gross=manual_totals["gross_pay"],
        expected_net=manual_totals["net_pay"],
    )

    frappe.db.commit()

    return {
        "slip_name": slip.name,
        "hours": summary["hours"],
        "payment_days": summary["payment_days"],
        "total_working_days": summary["total_working_days"],
        "absent_days": summary["absent_days"],
        "hourly_rate": flt(hourly_rate, 2),
        "gross": gross,
        "ss_employee": ss_employee,
        "medicare_employee": medicare_employee,
        "federal_withholding": flt(federal_withholding, 2),
        "colorado_withholding": flt(colorado_withholding, 2),
        "ss_employer": ss_employer,
        "medicare_employer": medicare_employer,
        "ytd_gross_before_period": ytd_before,
        "gross_pay_field": flt(getattr(slip, "gross_pay", 0.0), 2),
        "total_deduction_field": flt(getattr(slip, "total_deduction", 0.0), 2),
        "net_pay": flt(getattr(slip, "net_pay", 0.0), 2),
        "salary_structure_on_slip": getattr(slip, "salary_structure", None),
        "issues": issues,
        "diagnostic": diagnose_salary_slip_math(slip.name),
    }
