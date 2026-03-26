import json

import frappe
from frappe import _
from frappe.utils import getdate

from rootedops_payroll.services.payroll_engine import (
    run_batched_hourly_payroll,
    create_consolidated_payroll_journal_entry_draft,
    get_employees_with_attendance_in_period,
)

def _get_employees_for_payroll_entry(ctx):
    employees = get_employees_with_attendance_in_period(
        start_date=ctx["start_date"],
        end_date=ctx["end_date"],
        company=ctx["company"],
    )

    if not employees:
        frappe.throw(
            _("No employees with attendance were found for {0} to {1} in {2}.").format(
                ctx["start_date"], ctx["end_date"], ctx["company"]
            )
        )

    return employees

def _get_payroll_entry_context(payroll_entry_name: str):
    if not frappe.db.exists("Payroll Entry", payroll_entry_name):
        frappe.throw(_("Payroll Entry {0} not found.").format(payroll_entry_name))

    pe = frappe.get_doc("Payroll Entry", payroll_entry_name)

    if not pe.company:
        frappe.throw(_("Payroll Entry must have a Company."))

    if not pe.start_date or not pe.end_date:
        frappe.throw(_("Payroll Entry must have Start Date and End Date."))

    return pe, {
        "company": pe.company,
        "start_date": getdate(pe.start_date),
        "end_date": getdate(pe.end_date),
    }

@frappe.whitelist()
def preview_attendance_payroll(payroll_entry_name: str):
    pe, ctx = _get_payroll_entry_context(payroll_entry_name)
    employees = _get_employees_for_payroll_entry(ctx)

    result = run_batched_hourly_payroll(
        employees=employees,
        start_date=ctx["start_date"],
        end_date=ctx["end_date"],
        company=ctx["company"],
    )

    return {
        "payroll_entry": pe.name,
        "employees": employees,
        "summary": {
            "employee_count": result.get("employee_count", 0),
            "salary_slip_names": result.get("salary_slip_names", []),
            "consolidated_liability_summary": result.get("consolidated_liability_summary"),
            "consolidated_register": result.get("consolidated_register"),
            "consolidated_journal_entry_preview": result.get("consolidated_journal_entry_preview"),
            "auto_attendance_result": result.get("auto_attendance_result"),
            "payroll_results": result.get("payroll_results", []),
        },
    }

@frappe.whitelist()
def create_or_refresh_draft_salary_slips(payroll_entry_name: str):
    pe, ctx = _get_payroll_entry_context(payroll_entry_name)
    employees = _get_employees_for_payroll_entry(ctx)

    result = run_batched_hourly_payroll(
        employees=employees,
        start_date=ctx["start_date"],
        end_date=ctx["end_date"],
        company=ctx["company"],
    )

    return {
        "payroll_entry": pe.name,
        "employees": employees,
        "employee_count": result.get("employee_count", 0),
        "salary_slip_names": result.get("salary_slip_names", []),
        "payroll_results": result.get("payroll_results", []),
        "consolidated_liability_summary": result.get("consolidated_liability_summary"),
    }

@frappe.whitelist()
def create_consolidated_draft_journal_entry(payroll_entry_name: str):
    pe, ctx = _get_payroll_entry_context(payroll_entry_name)
    employees = _get_employees_for_payroll_entry(ctx)

    result = run_batched_hourly_payroll(
        employees=employees,
        start_date=ctx["start_date"],
        end_date=ctx["end_date"],
        company=ctx["company"],
    )

    je_preview = result.get("consolidated_journal_entry_preview")
    if not je_preview or not je_preview.get("is_ready_to_create"):
        frappe.throw(_("Consolidated Journal Entry preview is not ready to create."))

    payroll_results = result.get("payroll_results", [])
    if not payroll_results:
        frappe.throw(_("No payroll results were generated for this Payroll Entry."))

    je = create_consolidated_payroll_journal_entry_draft(
        payroll_results=payroll_results,
        posting_date=ctx["end_date"],
        company=ctx["company"],
    )

    journal_entry_name = None

    if isinstance(je, dict):
        journal_entry_name = (
            je.get("name")
            or je.get("journal_entry")
            or je.get("journal_entry_name")
        )
    else:
        journal_entry_name = getattr(je, "name", None)

    return {
        "payroll_entry": pe.name,
        "employees": employees,
        "journal_entry": journal_entry_name,
        "journal_entry_result": je,
        "salary_slip_names": result.get("salary_slip_names", []),
    }
