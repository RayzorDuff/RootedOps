import frappe
from frappe import _
from frappe.utils import getdate, now_datetime

from rootedops_payroll.services.payroll_engine import (
    build_consolidated_payroll_cash_flow_preview,
    build_consolidated_payroll_journal_entry_preview,
    create_consolidated_employee_payment_journal_entry_draft,
    create_consolidated_payroll_journal_entry_draft,
    create_consolidated_tax_reserve_transfer_journal_entry_draft,
    finalize_custom_salary_slip,
    get_employee_payroll_context,
    get_employees_with_attendance_in_period,
    medicare_employer_amount,
    repair_salary_slip_totals,
    run_batched_hourly_payroll,
    ss_employer_amount,
    submit_custom_salary_slip,
    summarize_consolidated_payroll_liabilities,
    ytd_gross_before_period,
)

PAYROLL_ENTRY_FIELD_CONSOLIDATED_JE = "rootedops_consolidated_journal_entry"
PAYROLL_ENTRY_FIELD_EMPLOYEE_PAYMENT_JE = "rootedops_employee_payment_journal_entry"
PAYROLL_ENTRY_FIELD_TAX_RESERVE_TRANSFER_JE = "rootedops_tax_reserve_transfer_journal_entry"


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

def _require_payroll_entry_columns(*fieldnames):
    missing = [
        fieldname
        for fieldname in fieldnames
        if not frappe.db.has_column("Payroll Entry", fieldname)
    ]
    if missing:
        frappe.throw(
            _(
                "Payroll Entry is missing required custom fields: {0}. "
                "Run the Payroll Entry custom field setup before using downstream JE actions."
            ).format(", ".join(missing))
        )

def _get_employees_for_payroll_entry(pe, ctx):
    selected_employees = []

    for row in (pe.get("employees") or []):
        employee = row.get("employee") if isinstance(row, dict) else getattr(row, "employee", None)
        if employee:
            selected_employees.append(employee)

    selected_employees = list(dict.fromkeys(selected_employees))

    if selected_employees:
        return selected_employees

    employees = get_employees_with_attendance_in_period(
        start_date=ctx["start_date"],
        end_date=ctx["end_date"],
        company=ctx["company"],
    )

    if not employees:
        frappe.throw(
            _("No employees were selected on Payroll Entry, and no employees with attendance were found for {0} to {1} in {2}.").format(
                ctx["start_date"], ctx["end_date"], ctx["company"]
            )
        )

    return employees

def _build_summary_text(result):
    liability = result.get("consolidated_liability_summary") or {}
    je_preview = result.get("consolidated_journal_entry_preview") or {}

    lines = [
        f"Employees: {result.get('employee_count', 0)}",
        f"Gross Wages: {liability.get('gross_wages', 0)}",
        f"Net Pay: {liability.get('net_pay', 0)}",
        f"Employee Taxes: {liability.get('employee_tax_total', 0)}",
        f"Employer Taxes: {liability.get('employer_tax_total', 0)}",
        f"Total Payroll Expense: {liability.get('total_payroll_expense', 0)}",
        f"JE Balanced: {'Yes' if je_preview.get('is_balanced') else 'No'}",
        f"Salary Slips: {len(result.get('salary_slip_names', []))}",
    ]
    return "\n".join(lines)


def _write_payroll_entry_summary(pe, result, journal_entry_name=None):
    updates = {
        "rootedops_salary_slip_count": len(result.get("salary_slip_names", [])),
        "rootedops_payroll_summary": _build_summary_text(result),
        "rootedops_last_processed_on": now_datetime(),
    }

    if journal_entry_name:
        updates["rootedops_consolidated_journal_entry"] = journal_entry_name

    pe.db_set(updates, update_modified=True)


def _get_existing_link(pe, fieldname, label):
    existing = pe.get(fieldname)
    if existing:
        frappe.throw(_("This Payroll Entry already has a {0}: {1}").format(label, existing))


def _write_payroll_entry_links(pe, **updates):
    filtered = {k: v for k, v in updates.items() if v}
    if filtered:
        pe.db_set(filtered, update_modified=True)


def _extract_journal_entry_name(result):
    if isinstance(result, dict):
        return result.get("journal_entry_name") or result.get("journal_entry") or result.get("name")
    return getattr(result, "name", None)


def _salary_component_amount(slip, component_name: str) -> float:
    total = 0.0
    for row in list(slip.earnings) + list(slip.deductions):
        if (row.salary_component or "") == component_name:
            total += float(row.amount or 0)
    return round(total, 2)


def _build_payroll_result_from_existing_slip(slip_name: str):
    slip = frappe.get_doc("Salary Slip", slip_name)
    payroll_ctx = get_employee_payroll_context(slip.employee, company=slip.company)

    gross = float(slip.gross_pay or 0)
    total_deduction = float(slip.total_deduction or 0)
    net_pay = float(slip.net_pay or 0)

    ss_employee = _salary_component_amount(slip, "Social Security")
    medicare_employee = _salary_component_amount(slip, "Medicare")
    federal_withholding = _salary_component_amount(slip, "Federal Withholding")
    colorado_withholding = _salary_component_amount(slip, "Colorado Withholding")

    ytd_before = ytd_gross_before_period(
        slip.employee,
        slip.start_date,
        exclude_slip_name=slip.name,
    )

    ss_employer = ss_employer_amount(gross, ytd_before)
    medicare_employer = medicare_employer_amount(gross)

    hourly_wage = _salary_component_amount(slip, "Hourly Wage")
    overnight_shift_pay = _salary_component_amount(slip, "Overnight Shift Pay")

    default_flat = float(
        frappe.db.get_value("Employee", slip.employee, "rootedops_overnight_flat_amount") or 100.0
    )
    overnight_shift_count = 0
    if default_flat and overnight_shift_pay:
        overnight_shift_count = int(round(overnight_shift_pay / default_flat))

    employee_tax_total = round(
        ss_employee + medicare_employee + federal_withholding + colorado_withholding, 2
    )
    employer_tax_total = round(ss_employer + medicare_employer, 2)

    return {
        "employee": slip.employee,
        "employee_name": slip.employee_name,
        "slip_name": slip.name,
        "company": slip.company,
        "currency": slip.currency,
        "payment_days": float(slip.payment_days or 0),
        "total_working_days": float(slip.total_working_days or 0),
        "hours": float(getattr(slip, "total_working_hours", 0) or 0),
        "hourly_hours": float(getattr(slip, "total_working_hours", 0) or 0),
        "hourly_gross": round(hourly_wage, 2),
        "overnight_flat_pay": round(overnight_shift_pay, 2),
        "overnight_shift_count": overnight_shift_count,
        "gross": round(gross, 2),
        "gross_pay_field": round(gross, 2),
        "total_deduction_field": round(total_deduction, 2),
        "net_pay": round(net_pay, 2),
        "ss_employee": round(ss_employee, 2),
        "medicare_employee": round(medicare_employee, 2),
        "federal_withholding": round(federal_withholding, 2),
        "colorado_withholding": round(colorado_withholding, 2),
        "employee_tax_total": round(employee_tax_total, 2),
        "ss_employer": round(ss_employer, 2),
        "medicare_employer": round(medicare_employer, 2),
        "employer_tax_total": round(employer_tax_total, 2),
        "total_payroll_expense": round(gross + employer_tax_total, 2),
        "payroll_payable_account": payroll_ctx.get("payroll_payable_account"),
        "cost_center": payroll_ctx.get("cost_center"),
    }


def _build_result_from_existing_salary_slips(pe, ctx, employees, submitted_only=False):
    slips = _get_salary_slips_for_payroll_entry(employees, ctx)
    if submitted_only:
        slips = [row for row in slips if row.get("docstatus") == 1]

    if not slips:
        return None

    payroll_results = [
        _build_payroll_result_from_existing_slip(row["name"])
        for row in slips
    ]

    return {
        "employee_count": len(payroll_results),
        "salary_slip_names": [row["slip_name"] for row in payroll_results],
        "payroll_results": payroll_results,
        "consolidated_liability_summary": summarize_consolidated_payroll_liabilities(payroll_results),
        "consolidated_journal_entry_preview": build_consolidated_payroll_journal_entry_preview(
            payroll_results=payroll_results,
            posting_date=ctx["end_date"],
            company=ctx["company"],
        ),
    }


def _get_existing_link(pe, fieldname, label):
    existing = pe.get(fieldname)
    if existing and not frappe.db.exists("Journal Entry", existing):
        pe.db_set(fieldname, None, update_modified=False)
        pe.reload()
        existing = None

    if existing:
        frappe.throw(_("This Payroll Entry already has a {0}: {1}").format(label, existing))


def _finalize_salary_slips_in_result(result):
    slip_names = list(dict.fromkeys(result.get("salary_slip_names", []) or []))
    finalized = []

    for slip_name in slip_names:
        finalize_custom_salary_slip(slip_name)
        finalized.append(slip_name)

    result["salary_slip_names"] = finalized
    return finalized


def _get_salary_slips_for_payroll_entry(employees, ctx):
    if not employees:
        return []

    return frappe.get_all(
        "Salary Slip",
        filters={
            "employee": ["in", employees],
            "start_date": ctx["start_date"],
            "end_date": ctx["end_date"],
            "docstatus": ["!=", 2],
        },
        fields=["name", "employee", "docstatus"],
        order_by="creation asc",
    )


def _run_payroll_for_entry(pe, ctx, finalize_slips=True):
    employees = _get_employees_for_payroll_entry(pe, ctx)
    result = run_batched_hourly_payroll(
        employees=employees,
        start_date=ctx["start_date"],
        end_date=ctx["end_date"],
        company=ctx["company"],
    )

    if finalize_slips:
        _finalize_salary_slips_in_result(result)

    return employees, result


@frappe.whitelist()
def preview_attendance_payroll(payroll_entry_name: str):
    pe, ctx = _get_payroll_entry_context(payroll_entry_name)
    employees, result = _run_payroll_for_entry(pe, ctx)

    _write_payroll_entry_summary(pe, result)

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
def preview_payroll_cash_flow(payroll_entry_name: str):
    pe, ctx = _get_payroll_entry_context(payroll_entry_name)
    employees, result = _run_payroll_for_entry(pe, ctx)

    cash_flow_preview = build_consolidated_payroll_cash_flow_preview(
        payroll_results=result.get("payroll_results", []),
        company=ctx["company"],
        posting_date=ctx["end_date"],
    )

    _write_payroll_entry_summary(pe, result)

    return {
        "payroll_entry": pe.name,
        "employees": employees,
        "summary": {
            "employee_count": result.get("employee_count", 0),
            "salary_slip_names": result.get("salary_slip_names", []),
            "consolidated_liability_summary": result.get("consolidated_liability_summary"),
            "consolidated_journal_entry_preview": result.get("consolidated_journal_entry_preview"),
            "consolidated_cash_flow_preview": cash_flow_preview,
            "payroll_results": result.get("payroll_results", []),
        },
    }


@frappe.whitelist()
def submit_draft_salary_slips(payroll_entry_name: str):
    pe, ctx = _get_payroll_entry_context(payroll_entry_name)
    employees = _get_employees_for_payroll_entry(pe, ctx)

    slips = _get_salary_slips_for_payroll_entry(employees, ctx)
    if not slips:
        frappe.throw(_("No Salary Slips were found for this Payroll Entry period."))

    submitted = []
    already_submitted = []

    for row in slips:
        if row.get("docstatus") == 1:
            already_submitted.append(row["name"])
            continue

        slip = submit_custom_salary_slip(row["name"])
        submitted.append(slip.name)

    # Do not rerun payroll here. Once slips are submitted, the payroll rebuild path
    # will correctly block on existing submitted slips.
    pe.db_set(
        {"rootedops_last_processed_on": now_datetime()},
        update_modified=True,
    )

    return {
        "payroll_entry": pe.name,
        "employees": employees,
        "submitted_salary_slip_names": submitted,
        "already_submitted_salary_slip_names": already_submitted,
        "salary_slip_names": [row["name"] for row in slips],
        "employee_count": len(employees),
    }


@frappe.whitelist()
def create_or_refresh_draft_salary_slips(payroll_entry_name: str):
    pe, ctx = _get_payroll_entry_context(payroll_entry_name)
    employees, result = _run_payroll_for_entry(pe, ctx, finalize_slips=True)

    _write_payroll_entry_summary(pe, result)

    return {
        "payroll_entry": pe.name,
        "employees": employees,
        "employee_count": result.get("employee_count", 0),
        "salary_slip_names": result.get("salary_slip_names", []),
        "payroll_results": result.get("payroll_results", []),
        "consolidated_liability_summary": result.get("consolidated_liability_summary"),
        "finalized": True,
    }


@frappe.whitelist()
def create_consolidated_draft_journal_entry(payroll_entry_name: str):
    pe, ctx = _get_payroll_entry_context(payroll_entry_name)
    employees = _get_employees_for_payroll_entry(pe, ctx)

    _get_existing_link(pe, PAYROLL_ENTRY_FIELD_CONSOLIDATED_JE, "consolidated Journal Entry")

    # Prefer submitted slips if they already exist for this period.
    result = _build_result_from_existing_salary_slips(pe, ctx, employees, submitted_only=True)
    if result is None:
        result = run_batched_hourly_payroll(
            employees=employees,
            start_date=ctx["start_date"],
            end_date=ctx["end_date"],
            company=ctx["company"],
        )

    payroll_results = result.get("payroll_results", [])
    if not payroll_results:
        frappe.throw(_("No payroll results were generated for this Payroll Entry."))

    je_preview = result.get("consolidated_journal_entry_preview") or {}
    if not je_preview or not je_preview.get("is_ready_to_create"):
        frappe.throw(_("Consolidated Journal Entry preview is not ready to create."))

    je = create_consolidated_payroll_journal_entry_draft(
        payroll_results=payroll_results,
        posting_date=ctx["end_date"],
        company=ctx["company"],
    )

    journal_entry_name = _extract_journal_entry_name(je)

    _write_payroll_entry_summary(pe, result, journal_entry_name=journal_entry_name)

    return {
        "payroll_entry": pe.name,
        "employees": employees,
        "journal_entry": journal_entry_name,
        "salary_slip_names": result.get("salary_slip_names", []),
    }


@frappe.whitelist()
def create_employee_payment_draft_journal_entry(payroll_entry_name: str):
    _require_payroll_entry_columns(
        PAYROLL_ENTRY_FIELD_CONSOLIDATED_JE,
        PAYROLL_ENTRY_FIELD_EMPLOYEE_PAYMENT_JE,
    )

    pe, ctx = _get_payroll_entry_context(payroll_entry_name)
    _get_existing_link(pe, PAYROLL_ENTRY_FIELD_EMPLOYEE_PAYMENT_JE, "employee payment Journal Entry")

    if not pe.get(PAYROLL_ENTRY_FIELD_CONSOLIDATED_JE):
        frappe.throw(_("Create the consolidated payroll accrual Journal Entry first."))

    employees = _get_employees_for_payroll_entry(pe, ctx)
    result = _build_result_from_existing_salary_slips(pe, ctx, employees, submitted_only=True)
    if result is None:
        frappe.throw(_("No submitted Salary Slips were found for this Payroll Entry period."))

    payroll_results = result.get("payroll_results", [])
    if not payroll_results:
        frappe.throw(_("No payroll results were generated for this Payroll Entry."))

    je_result = create_consolidated_employee_payment_journal_entry_draft(
        payroll_results=payroll_results,
        posting_date=ctx["end_date"],
        company=ctx["company"],
    )
    journal_entry_name = _extract_journal_entry_name(je_result)

    _write_payroll_entry_summary(pe, result)
    _write_payroll_entry_links(pe, **{PAYROLL_ENTRY_FIELD_EMPLOYEE_PAYMENT_JE: journal_entry_name})

    return {
        "payroll_entry": pe.name,
        "employees": employees,
        "journal_entry": journal_entry_name,
        "salary_slip_names": result.get("salary_slip_names", []),
        "recommended_bank_accounts": je_result.get("recommended_bank_accounts"),
        "liability_summary": je_result.get("liability_summary"),
    }


@frappe.whitelist()
def create_tax_reserve_transfer_draft_journal_entry(payroll_entry_name: str):
    _require_payroll_entry_columns(
        PAYROLL_ENTRY_FIELD_CONSOLIDATED_JE,
        PAYROLL_ENTRY_FIELD_TAX_RESERVE_TRANSFER_JE,
    )

    pe, ctx = _get_payroll_entry_context(payroll_entry_name)
    _get_existing_link(pe, PAYROLL_ENTRY_FIELD_TAX_RESERVE_TRANSFER_JE, "tax reserve transfer Journal Entry")

    if not pe.get(PAYROLL_ENTRY_FIELD_CONSOLIDATED_JE):
        frappe.throw(_("Create the consolidated payroll accrual Journal Entry first."))

    employees = _get_employees_for_payroll_entry(pe, ctx)
    result = _build_result_from_existing_salary_slips(pe, ctx, employees, submitted_only=True)
    if result is None:
        frappe.throw(_("No submitted Salary Slips were found for this Payroll Entry period."))

    payroll_results = result.get("payroll_results", [])
    if not payroll_results:
        frappe.throw(_("No payroll results were generated for this Payroll Entry."))

    je_result = create_consolidated_tax_reserve_transfer_journal_entry_draft(
        payroll_results=payroll_results,
        posting_date=ctx["end_date"],
        company=ctx["company"],
    )
    journal_entry_name = _extract_journal_entry_name(je_result)

    _write_payroll_entry_summary(pe, result)
    _write_payroll_entry_links(pe, **{PAYROLL_ENTRY_FIELD_TAX_RESERVE_TRANSFER_JE: journal_entry_name})

    return {
        "payroll_entry": pe.name,
        "employees": employees,
        "journal_entry": journal_entry_name,
        "salary_slip_names": result.get("salary_slip_names", []),
        "recommended_bank_accounts": je_result.get("recommended_bank_accounts"),
        "liability_summary": je_result.get("liability_summary"),
    }
