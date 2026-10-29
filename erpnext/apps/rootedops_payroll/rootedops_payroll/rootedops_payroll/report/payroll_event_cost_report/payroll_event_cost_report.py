from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, getdate

from rootedops_payroll.services.payroll_engine import (
    MEDICARE_RATE,
    PAY_MODEL_HYBRID_OVERNIGHT,
    PAY_MODEL_STANDARD_HOURLY,
    SS_RATE,
    calculate_colorado_famli_premium,
    colorado_ui_amount,
    colorado_ui_company_profile,
    get_checkin_sessions,
    get_employee_payroll_context,
    get_employee_tax_profile,
    medicare_employer_amount,
    split_session_into_hybrid_segments,
    ss_employer_amount,
    ytd_gross_before_period,
    ytd_ui_gross_before_period,
)


def execute(filters=None):
    filters = frappe._dict(filters or {})
    company, employee, window_start, window_end = _validate_filters(filters)
    profile = get_employee_tax_profile(employee) or {}

    hourly_rate = flt(profile.get("hourly_rate"), 2)
    if hourly_rate <= 0:
        frappe.throw(_("Employee {0} does not have a positive RootedOps Hourly Rate.").format(employee))

    pay_model = _normalize_pay_model(profile.get("pay_model"))
    overnight_flat_amount = flt(profile.get("overnight_flat_amount") or 100.0, 2)

    compensation_rows = _build_compensation_rows(
        employee=employee,
        window_start=window_start,
        window_end=window_end,
        pay_model=pay_model,
        hourly_rate=hourly_rate,
        overnight_flat_amount=overnight_flat_amount,
    )
    if not compensation_rows:
        frappe.throw(
            _("No compensated Employee Checkin time overlaps the selected event window.")
        )

    gross_wages = flt(sum(row["amount"] for row in compensation_rows), 2)
    employer_tax = _employer_tax_detail(
        company=company,
        employee=employee,
        event_date=getdate(window_start),
        payroll_date=getdate(window_end),
        gross_wages=gross_wages,
    )

    data = list(compensation_rows)
    data.append(_subtotal_row(_("Gross Wages"), gross_wages))
    data.extend(_employer_tax_rows(employer_tax))
    data.append(
        {
            "category": _("TOTAL"),
            "description": _("Total employer payroll expense"),
            "basis": _("Gross wages + employer payroll taxes"),
            "amount": flt(gross_wages + employer_tax["employer_tax_total"], 2),
        }
    )

    compensated_hours = flt(sum(row.get("hours") or 0 for row in compensation_rows), 2)
    message = _(
        "This report is a read-only event-cost allocation from Employee Checkin records and "
        "RootedOps employer-tax rules. Federal and Colorado income-tax withholding are not "
        "allocated to an event because they are employee deductions calculated for the full payroll period."
    )

    return (
        _get_columns(),
        data,
        message,
        None,
        _get_report_summary(
            compensated_hours=compensated_hours,
            gross_wages=gross_wages,
            employer_tax_total=employer_tax["employer_tax_total"],
            total_payroll_expense=flt(gross_wages + employer_tax["employer_tax_total"], 2),
            pay_model=pay_model,
        ),
    )


def _validate_filters(filters):
    company = filters.get("company")
    employee = filters.get("employee")
    window_start = filters.get("window_start")
    window_end = filters.get("window_end")

    if not company:
        frappe.throw(_("Company is required."))
    if not employee:
        frappe.throw(_("Employee is required."))
    if not window_start or not window_end:
        frappe.throw(_("Event Start and Event End are required."))

    window_start = get_datetime(window_start)
    window_end = get_datetime(window_end)
    if window_end <= window_start:
        frappe.throw(_("Event End must be after Event Start."))

    payroll_context = get_employee_payroll_context(employee)
    if payroll_context["company"] != company:
        frappe.throw(
            _("Employee {0} belongs to {1}, not {2}.").format(
                employee,
                payroll_context["company"],
                company,
            )
        )

    return company, employee, window_start, window_end


def _normalize_pay_model(value):
    pay_model = (value or PAY_MODEL_STANDARD_HOURLY).strip().lower().replace(" ", "_")
    if pay_model not in (PAY_MODEL_STANDARD_HOURLY, PAY_MODEL_HYBRID_OVERNIGHT):
        frappe.throw(_("Unsupported RootedOps pay model: {0}").format(pay_model))
    return pay_model


def _build_compensation_rows(
    employee,
    window_start,
    window_end,
    pay_model,
    hourly_rate,
    overnight_flat_amount,
):
    sessions = get_checkin_sessions(employee, getdate(window_start), getdate(window_end))
    rows = []

    for session in sessions:
        session_start = get_datetime(session["start"])
        session_end = get_datetime(session["end"])
        if session_end <= window_start or session_start >= window_end:
            continue

        if pay_model == PAY_MODEL_HYBRID_OVERNIGHT:
            segments = split_session_into_hybrid_segments(session)["segments"]
        else:
            segments = [
                {
                    "type": "hourly",
                    "start": session_start,
                    "end": session_end,
                    "hours": flt((session_end - session_start).total_seconds() / 3600.0, 2),
                }
            ]

        for segment in segments:
            segment_start = get_datetime(segment["start"])
            segment_end = get_datetime(segment["end"])

            if segment["type"] == "overnight_flat":
                # The flat amount represents the entire canonical 22:00 -> 06:00
                # block. Do not allocate a partial flat block to an evidence window.
                if segment_start < window_start or segment_end > window_end:
                    continue
                rows.append(
                    _compensation_row(
                        session=session,
                        description=_("Overnight flat shift"),
                        start=segment_start,
                        end=segment_end,
                        hours=flt(segment.get("hours") or 8.0, 2),
                        rate=overnight_flat_amount,
                        basis=_("Flat amount per full 22:00-06:00 overnight block"),
                        amount=overnight_flat_amount,
                    )
                )
                continue

            clipped_start = max(segment_start, window_start)
            clipped_end = min(segment_end, window_end)
            if clipped_end <= clipped_start:
                continue

            hours = flt((clipped_end - clipped_start).total_seconds() / 3600.0, 2)
            rows.append(
                _compensation_row(
                    session=session,
                    description=_("Hourly nanny time"),
                    start=clipped_start,
                    end=clipped_end,
                    hours=hours,
                    rate=hourly_rate,
                    basis=_('{0} hours x ${1:,.2f}/hour').format(hours, hourly_rate),
                    amount=flt(hours * hourly_rate, 2),
                )
            )

    rows.sort(key=lambda row: (row.get("start") or window_start, row.get("description") or ""))
    return rows


def _compensation_row(session, description, start, end, hours, rate, basis, amount):
    source = _("IN {0} / OUT {1}").format(
        session.get("in_name") or _("unknown"),
        session.get("out_name") or _("unknown"),
    )
    return {
        "category": _("Compensation"),
        "description": description,
        "start": start,
        "end": end,
        "hours": flt(hours, 2),
        "rate": flt(rate, 2),
        "basis": basis,
        "source": source,
        "amount": flt(amount, 2),
    }


def _employer_tax_detail(company, employee, event_date, payroll_date, gross_wages):
    ytd_before = ytd_gross_before_period(employee, event_date)
    ss_employer = ss_employer_amount(gross_wages, ytd_before)
    medicare_employer = medicare_employer_amount(gross_wages)

    ui_profile = colorado_ui_company_profile(company, payroll_date)
    ui_ytd_before = ytd_ui_gross_before_period(employee, event_date)
    ui_detail = colorado_ui_amount(
        gross_wages,
        ui_ytd_before,
        ui_profile["rate_percent"] if ui_profile["enabled"] else 0.0,
        ui_profile["wage_base"],
    )

    famli = calculate_colorado_famli_premium(
        company,
        gross_wages,
        ytd_before,
        payroll_date,
    )

    employer_tax_total = flt(
        ss_employer
        + medicare_employer
        + ui_detail["amount"]
        + famli["employer_expense"],
        2,
    )

    return {
        "social_security": ss_employer,
        "medicare": medicare_employer,
        "colorado_ui": ui_detail,
        "colorado_ui_profile": ui_profile,
        "colorado_famli": famli,
        "employer_tax_total": employer_tax_total,
    }


def _employer_tax_rows(detail):
    ui = detail["colorado_ui"]
    ui_profile = detail["colorado_ui_profile"]
    famli = detail["colorado_famli"]
    famli_settings = famli.get("settings") or {}

    rows = [
        {
            "category": _("Employer Tax"),
            "description": _("Employer Social Security"),
            "basis": _('{0:.2f}% of applicable Social Security taxable wages').format(SS_RATE * 100),
            "amount": detail["social_security"],
        },
        {
            "category": _("Employer Tax"),
            "description": _("Employer Medicare"),
            "basis": _('{0:.2f}% of gross wages').format(MEDICARE_RATE * 100),
            "amount": detail["medicare"],
        },
        {
            "category": _("Employer Tax"),
            "description": _("Colorado Unemployment Insurance"),
            "basis": _('{0:.4f}% of ${1:,.2f} taxable wages').format(
                flt(ui_profile.get("rate_percent"), 4),
                flt(ui.get("taxable_wages"), 2),
            ),
            "amount": flt(ui.get("amount"), 2),
        },
        {
            "category": _("Employer Tax"),
            "description": _("Employer Colorado FAMLI"),
            "basis": _(
                "Configured employer expense; employer rate {0:.4f}%"
            ).format(flt(famli_settings.get("employer_rate"), 4)),
            "amount": flt(famli.get("employer_expense"), 2),
        },
        {
            "category": _("Employer Tax"),
            "description": _("Employer Tax Total"),
            "basis": _("Social Security + Medicare + Colorado UI + employer Colorado FAMLI"),
            "amount": detail["employer_tax_total"],
        },
    ]
    return rows


def _subtotal_row(description, amount):
    return {
        "category": _("Subtotal"),
        "description": description,
        "amount": flt(amount, 2),
    }


def _get_report_summary(
    compensated_hours,
    gross_wages,
    employer_tax_total,
    total_payroll_expense,
    pay_model,
):
    return [
        {
            "value": compensated_hours,
            "indicator": "Blue",
            "label": _("Compensated Hours"),
            "datatype": "Float",
        },
        {
            "value": gross_wages,
            "indicator": "Green",
            "label": _("Gross Wages"),
            "datatype": "Currency",
        },
        {
            "value": employer_tax_total,
            "indicator": "Orange",
            "label": _("Employer Taxes"),
            "datatype": "Currency",
        },
        {
            "value": total_payroll_expense,
            "indicator": "Purple",
            "label": _("Total Payroll Expense"),
            "datatype": "Currency",
        },
        {
            "value": pay_model,
            "indicator": "Gray",
            "label": _("Pay Model"),
            "datatype": "Data",
        },
    ]


def _get_columns():
    return [
        {
            "fieldname": "category",
            "label": _("Category"),
            "fieldtype": "Data",
            "width": 115,
        },
        {
            "fieldname": "description",
            "label": _("Description"),
            "fieldtype": "Data",
            "width": 205,
        },
        {
            "fieldname": "start",
            "label": _("Start"),
            "fieldtype": "Datetime",
            "width": 155,
        },
        {
            "fieldname": "end",
            "label": _("End"),
            "fieldtype": "Datetime",
            "width": 155,
        },
        {
            "fieldname": "hours",
            "label": _("Hours"),
            "fieldtype": "Float",
            "precision": 2,
            "width": 80,
        },
        {
            "fieldname": "rate",
            "label": _("Rate / Flat Amount"),
            "fieldtype": "Currency",
            "width": 125,
        },
        {
            "fieldname": "basis",
            "label": _("Calculation Basis"),
            "fieldtype": "Data",
            "width": 330,
        },
        {
            "fieldname": "source",
            "label": _("Checkin Source"),
            "fieldtype": "Data",
            "width": 235,
        },
        {
            "fieldname": "amount",
            "label": _("Amount"),
            "fieldtype": "Currency",
            "width": 120,
        },
    ]
