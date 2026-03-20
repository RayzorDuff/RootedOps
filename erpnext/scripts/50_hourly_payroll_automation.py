"""RootedOps ERPNext hourly payroll automation.

Current scope:
- Attendance-based hours
- Gross pay from hourly rate
- Employee Social Security
- Employee Medicare
- Employer Social Security (reported in return value)
- Employer Medicare (reported in return value)

Not yet implemented:
- Federal withholding from W-4 / IRS 15-T
- Colorado withholding from state inputs

Run inside bench console with:
    exec(open("/home/frappe/frappe-bench/sites/50_hourly_payroll_automation.py").read(), globals())
"""

import frappe
from frappe.utils import flt

SS_WAGE_BASE_2026 = 184500.0
SS_RATE = 0.062
MEDICARE_RATE = 0.0145

def attendance_hours(employee, start_date, end_date):
    rows = frappe.get_all(
        "Attendance",
        filters={
            "employee": employee,
            "attendance_date": ["between", [start_date, end_date]],
            "docstatus": 1,
            "status": "Present"
        },
        fields=["working_hours"]
    )
    return sum(flt(r.working_hours) for r in rows)

def ytd_gross_before_period(employee, end_date):
    rows = frappe.get_all(
        "Salary Slip",
        filters={
            "employee": employee,
            "docstatus": ["<", 2],
            "end_date": ["<", end_date]
        },
        fields=["gross_pay"]
    )
    return sum(flt(r.gross_pay) for r in rows)

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

def rebuild_hourly_salary_slip(
    employee,
    start_date,
    end_date,
    hourly_rate,
    payroll_frequency="Weekly",
    salary_structure="Dank Mushrooms Weekly Test",
    company="Dank Mushrooms, LLC",
    federal_withholding=None,
    colorado_withholding=None
):
    existing = frappe.get_all(
        "Salary Slip",
        filters={
            "employee": employee,
            "start_date": start_date,
            "end_date": end_date,
            "docstatus": 0
        },
        pluck="name"
    )

    if existing:
        slip = frappe.get_doc("Salary Slip", existing[0])
    else:
        slip = frappe.get_doc({
            "doctype": "Salary Slip",
            "employee": employee,
            "company": company,
            "start_date": start_date,
            "end_date": end_date,
            "payroll_frequency": payroll_frequency
        })
        slip.insert(ignore_permissions=True)

    hours = attendance_hours(employee, start_date, end_date)
    gross = flt(hours * hourly_rate, 2)
    ytd_before = ytd_gross_before_period(employee, end_date)

    ss_employee = ss_employee_amount(gross, ytd_before)
    medicare_employee = medicare_employee_amount(gross)
    ss_employer = ss_employer_amount(gross, ytd_before)
    medicare_employer = medicare_employer_amount(gross)

    if federal_withholding is None:
        federal_withholding = 0.0
    if colorado_withholding is None:
        colorado_withholding = 0.0

    slip.get_emp_and_working_day_details()
    slip.set("earnings", [])
    slip.set("deductions", [])

    slip.append("earnings", {
        "salary_component": "Hourly Wage",
        "abbr": "Hourly",
        "amount": gross,
        "default_amount": gross,
        "depends_on_payment_days": 0
    })

    slip.append("deductions", {
        "salary_component": "Social Security",
        "abbr": "SocialSecurity",
        "amount": ss_employee,
        "default_amount": ss_employee,
        "depends_on_payment_days": 0
    })

    slip.append("deductions", {
        "salary_component": "Medicare",
        "abbr": "Medicare",
        "amount": medicare_employee,
        "default_amount": medicare_employee,
        "depends_on_payment_days": 0
    })

    if flt(federal_withholding):
        slip.append("deductions", {
            "salary_component": "Federal Withholding",
            "abbr": "FederalWH",
            "amount": flt(federal_withholding, 2),
            "default_amount": flt(federal_withholding, 2),
            "depends_on_payment_days": 0
        })

    if flt(colorado_withholding):
        slip.append("deductions", {
            "salary_component": "Colorado Withholding",
            "abbr": "ColoradoWH",
            "amount": flt(colorado_withholding, 2),
            "default_amount": flt(colorado_withholding, 2),
            "depends_on_payment_days": 0
        })

    slip.salary_structure = salary_structure
    slip.total_working_hours = flt(hours, 2)
    slip.calculate_net_pay()
    slip.save(ignore_permissions=True)
    frappe.db.commit()

    return {
        "slip_name": slip.name,
        "hours": hours,
        "gross": gross,
        "ss_employee": ss_employee,
        "medicare_employee": medicare_employee,
        "federal_withholding": flt(federal_withholding, 2),
        "colorado_withholding": flt(colorado_withholding, 2),
        "ss_employer": ss_employer,
        "medicare_employer": medicare_employer,
        "net_pay": slip.net_pay
    }
