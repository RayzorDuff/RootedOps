from __future__ import annotations

from calendar import monthrange
from datetime import date

import frappe
from frappe import _
from frappe.utils import cint, flt

from rootedops_payroll.services.payroll_engine import (
    MEDICARE_RATE,
    calculate_colorado_famli_premium,
    colorado_ui_amount,
    colorado_ui_company_profile,
    ss_employer_amount,
    ytd_gross_before_period,
    ytd_ui_gross_before_period,
)


QUARTER_START_MONTH = {
    "Q1": 1,
    "Q2": 4,
    "Q3": 7,
    "Q4": 10,
}


COMPONENT_COLUMNS = {
    "Federal Withholding": "federal_withholding",
    "Colorado Withholding": "colorado_withholding",
    "Social Security": "social_security_employee",
    "Medicare": "medicare_employee",
    "Colorado FAMLI": "colorado_famli_employee",
}


def execute(filters=None):
    filters = frappe._dict(filters or {})
    start_date, end_date = _get_quarter_dates(filters)
    docstatus_filter = _get_docstatus_filter(filters.get("salary_slip_status"))

    rows = _get_rows(
        company=filters.company,
        start_date=start_date,
        end_date=end_date,
        docstatus_filter=docstatus_filter,
    )
    total_row = _build_total_row(rows)
    data = rows + ([total_row] if rows else [])

    return (
        _get_columns(),
        data,
        None,
        _get_report_summary(rows, start_date, end_date),
    )


def _get_quarter_dates(filters):
    company = filters.get("company")
    if not company:
        frappe.throw(_("Company is required."))

    year = cint(filters.get("year"))
    if year < 1900 or year > 9999:
        frappe.throw(_("Enter a valid four-digit year."))

    quarter = filters.get("quarter")
    start_month = QUARTER_START_MONTH.get(quarter)
    if not start_month:
        frappe.throw(_("Select a valid quarter."))

    end_month = start_month + 2
    return date(year, start_month, 1), date(year, end_month, monthrange(year, end_month)[1])


def _get_docstatus_filter(status):
    if status == "Draft":
        return (0,)
    if status == "Draft and Submitted":
        return (0, 1)
    return (1,)


def _get_rows(company, start_date, end_date, docstatus_filter):
    slips = frappe.get_all(
        "Salary Slip",
        filters={
            "company": company,
            "posting_date": ["between", [start_date, end_date]],
            "docstatus": ["in", docstatus_filter],
        },
        fields=[
            "name",
            "employee",
            "employee_name",
            "posting_date",
            "start_date",
            "end_date",
            "gross_pay",
            "total_deduction",
            "net_pay",
            "docstatus",
        ],
        order_by="posting_date asc, employee asc, name asc",
    )

    if not slips:
        return []

    slip_names = [row.name for row in slips]
    deductions = frappe.get_all(
        "Salary Detail",
        filters={
            "parent": ["in", slip_names],
            "parenttype": "Salary Slip",
            "parentfield": "deductions",
            "salary_component": ["in", list(COMPONENT_COLUMNS)],
        },
        fields=["parent", "salary_component", "amount"],
    )

    deduction_map = {name: {} for name in slip_names}
    for row in deductions:
        key = COMPONENT_COLUMNS.get(row.salary_component)
        if key:
            deduction_map[row.parent][key] = flt(row.amount)

    ui_profile = colorado_ui_company_profile(company, end_date)
    data = []
    for slip in slips:
        component_values = deduction_map.get(slip.name, {})
        ui_ytd_before = ytd_ui_gross_before_period(
            slip.employee, slip.start_date, exclude_slip_name=slip.name
        )
        fica_ytd_before = ytd_gross_before_period(
            slip.employee, slip.start_date, exclude_slip_name=slip.name
        )
        employer_social_security = ss_employer_amount(slip.gross_pay, fica_ytd_before)
        employer_medicare = flt(slip.gross_pay * MEDICARE_RATE, 2)
        ui_detail = colorado_ui_amount(
            slip.gross_pay,
            ui_ytd_before,
            ui_profile["rate_percent"] if ui_profile["enabled"] else 0.0,
            ui_profile["wage_base"],
        )
        colorado_famli = calculate_colorado_famli_premium(
            company, slip.gross_pay, fica_ytd_before, slip.posting_date
        )
        data.append(
            {
                "salary_slip": slip.name,
                "employee": slip.employee,
                "employee_name": slip.employee_name,
                "posting_date": slip.posting_date,
                "period_start": slip.start_date,
                "period_end": slip.end_date,
                "status": _docstatus_label(slip.docstatus),
                "gross_pay": flt(slip.gross_pay),
                "federal_withholding": flt(component_values.get("federal_withholding")),
                "colorado_withholding": flt(component_values.get("colorado_withholding")),
                "social_security_employee": flt(component_values.get("social_security_employee")),
                "medicare_employee": flt(component_values.get("medicare_employee")),
                "colorado_famli_employee": flt(component_values.get("colorado_famli_employee")),
                "social_security_employer": employer_social_security,
                "medicare_employer": employer_medicare,
                "colorado_ui_gross_wages": ui_detail["gross_wages"],
                "colorado_ui_excess_wages": ui_detail["excess_wages"],
                "colorado_ui_taxable_wages": ui_detail["taxable_wages"],
                "colorado_ui_employer": ui_detail["amount"],
                "colorado_famli_employer": colorado_famli["employer_expense"],
                "colorado_famli_total_remittance": colorado_famli["total_remittance"],
                "colorado_famli_taxable_wages": colorado_famli["taxable_wages"],
                "employer_tax_total": flt(
                    employer_social_security
                    + employer_medicare
                    + ui_detail["amount"]
                    + colorado_famli["employer_expense"],
                    2,
                ),
                "total_deduction": flt(slip.total_deduction),
                "net_pay": flt(slip.net_pay),
            }
        )
    return data


def _build_total_row(rows):
    numeric_fields = (
        "gross_pay",
        "federal_withholding",
        "colorado_withholding",
        "social_security_employee",
        "medicare_employee",
        "colorado_famli_employee",
        "social_security_employer",
        "medicare_employer",
        "colorado_ui_gross_wages",
        "colorado_ui_excess_wages",
        "colorado_ui_taxable_wages",
        "colorado_ui_employer",
        "colorado_famli_employer",
        "colorado_famli_total_remittance",
        "colorado_famli_taxable_wages",
        "employer_tax_total",
        "total_deduction",
        "net_pay",
    )
    total = {
        "salary_slip": _("TOTAL"),
        "employee_name": _("Quarter totals"),
    }
    for fieldname in numeric_fields:
        total[fieldname] = sum(flt(row.get(fieldname)) for row in rows)
    return total


def _get_report_summary(rows, start_date, end_date):
    totals = _build_total_row(rows) if rows else {}
    return [
        {
            "value": totals.get("gross_pay", 0),
            "indicator": "Blue",
            "label": _("Gross Pay"),
            "datatype": "Currency",
        },
        {
            "value": totals.get("colorado_withholding", 0),
            "indicator": "Orange",
            "label": _("Colorado Withholding"),
            "datatype": "Currency",
        },
        {
            "value": totals.get("colorado_ui_employer", 0),
            "indicator": "Red",
            "label": _("Colorado UI"),
            "datatype": "Currency",
        },
        {
            "value": totals.get("employer_tax_total", 0),
            "indicator": "Purple",
            "label": _("Employer Taxes"),
            "datatype": "Currency",
        },
        {
            "value": totals.get("colorado_famli_total_remittance", 0),
            "indicator": "Orange",
            "label": _("Colorado FAMLI Remittance"),
            "datatype": "Currency",
        },
        {
            "value": len(rows),
            "indicator": "Green",
            "label": _("Salary Slips"),
            "datatype": "Int",
        },
        {
            "value": f"{start_date.isoformat()} to {end_date.isoformat()}",
            "indicator": "Gray",
            "label": _("Report Period"),
            "datatype": "Data",
        },
    ]


def _docstatus_label(docstatus):
    return {
        0: _("Draft"),
        1: _("Submitted"),
        2: _("Cancelled"),
    }.get(cint(docstatus), str(docstatus))


def _get_columns():
    return [
        {
            "fieldname": "salary_slip",
            "label": _("Salary Slip"),
            "fieldtype": "Link",
            "options": "Salary Slip",
            "width": 190,
        },
        {
            "fieldname": "employee",
            "label": _("Employee"),
            "fieldtype": "Link",
            "options": "Employee",
            "width": 125,
        },
        {
            "fieldname": "employee_name",
            "label": _("Employee Name"),
            "fieldtype": "Data",
            "width": 160,
        },
        {
            "fieldname": "posting_date",
            "label": _("Posting Date"),
            "fieldtype": "Date",
            "width": 105,
        },
        {
            "fieldname": "period_start",
            "label": _("Period Start"),
            "fieldtype": "Date",
            "width": 105,
        },
        {
            "fieldname": "period_end",
            "label": _("Period End"),
            "fieldtype": "Date",
            "width": 105,
        },
        {
            "fieldname": "status",
            "label": _("Status"),
            "fieldtype": "Data",
            "width": 90,
        },
        {
            "fieldname": "gross_pay",
            "label": _("Gross Pay"),
            "fieldtype": "Currency",
            "width": 115,
        },
        {
            "fieldname": "federal_withholding",
            "label": _("Federal Withholding"),
            "fieldtype": "Currency",
            "width": 140,
        },
        {
            "fieldname": "colorado_withholding",
            "label": _("Colorado Withholding"),
            "fieldtype": "Currency",
            "width": 145,
        },
        {
            "fieldname": "social_security_employee",
            "label": _("Social Security"),
            "fieldtype": "Currency",
            "width": 125,
        },
        {
            "fieldname": "medicare_employee",
            "label": _("Medicare"),
            "fieldtype": "Currency",
            "width": 105,
        },
        {
            "fieldname": "colorado_famli_employee",
            "label": _("Employee Colorado FAMLI"),
            "fieldtype": "Currency",
            "width": 160,
        },
        {
            "fieldname": "social_security_employer",
            "label": _("Employer Social Security"),
            "fieldtype": "Currency",
            "width": 155,
        },
        {
            "fieldname": "medicare_employer",
            "label": _("Employer Medicare"),
            "fieldtype": "Currency",
            "width": 135,
        },
        {
            "fieldname": "colorado_ui_gross_wages",
            "label": _("CO UI Gross Wages"),
            "fieldtype": "Currency",
            "width": 135,
        },
        {
            "fieldname": "colorado_ui_excess_wages",
            "label": _("CO UI Excess Wages"),
            "fieldtype": "Currency",
            "width": 140,
        },
        {
            "fieldname": "colorado_ui_taxable_wages",
            "label": _("CO UI Taxable Wages"),
            "fieldtype": "Currency",
            "width": 145,
        },
        {
            "fieldname": "colorado_ui_employer",
            "label": _("Colorado UI"),
            "fieldtype": "Currency",
            "width": 115,
        },
        {"fieldname": "colorado_famli_taxable_wages", "label": _("FAMLI Taxable Wages"), "fieldtype": "Currency", "width": 155},
        {"fieldname": "colorado_famli_employer", "label": _("Employer Colorado FAMLI"), "fieldtype": "Currency", "width": 165},
        {"fieldname": "colorado_famli_total_remittance", "label": _("FAMLI Remittance"), "fieldtype": "Currency", "width": 145},
        {
            "fieldname": "employer_tax_total",
            "label": _("Employer Tax Total"),
            "fieldtype": "Currency",
            "width": 140,
        },
        {
            "fieldname": "total_deduction",
            "label": _("Total Deductions"),
            "fieldtype": "Currency",
            "width": 130,
        },
        {
            "fieldname": "net_pay",
            "label": _("Net Pay"),
            "fieldtype": "Currency",
            "width": 115,
        },
    ]
