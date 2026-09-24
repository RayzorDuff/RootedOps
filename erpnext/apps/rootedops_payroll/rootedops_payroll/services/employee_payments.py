"""Employee payroll-payment configuration and audit-field foundation.

Issue #8 deliberately separates payroll calculation/accrual from settlement of
net pay to each employee.  Phase 1 only establishes the configuration and
structured metadata that later phases will use; it does not create, submit, or
cancel Journal Entries.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils import cint, getdate

PAYMENT_METHOD_ACH = "ACH"
PAYMENT_METHOD_VENMO = "Venmo"
PAYMENT_METHOD_APPLE_CASH = "Apple Pay / Apple Cash"
PAYMENT_METHOD_PAPER_CHECK = "Paper Check"
PAYMENT_METHOD_OTHER_MANUAL = "Other / Manual"

PAYMENT_METHODS = (
    PAYMENT_METHOD_ACH,
    PAYMENT_METHOD_VENMO,
    PAYMENT_METHOD_APPLE_CASH,
    PAYMENT_METHOD_PAPER_CHECK,
    PAYMENT_METHOD_OTHER_MANUAL,
)

PAYMENT_METHOD_OPTIONS = "\n" + "\n".join(PAYMENT_METHODS)

PAYMENT_STATUS_NOT_RECORDED = "Not Recorded"
PAYMENT_STATUS_DRAFT = "Payment JE Draft"
PAYMENT_STATUS_SUBMITTED = "Payment JE Submitted"
PAYMENT_STATUS_CANCELLED = "Payment JE Cancelled"
PAYMENT_STATUS_CONFLICT = "Payment JE Conflict"

PAYMENT_ACCOUNTING_MATCH = "Matches Salary Slip"
PAYMENT_ACCOUNTING_MISMATCH = "Accounting Mismatch"
PAYMENT_ACCOUNTING_NOT_RECORDED = "Not Recorded"

EMPLOYEE_PAYMENT_CUSTOM_FIELDS = {
    "Employee": [
        {
            "fieldname": "rootedops_payroll_payment_section",
            "label": "RootedOps Payroll Payment",
            "fieldtype": "Section Break",
            "insert_after": "rootedops_overnight_flat_amount",
            "collapsible": 1,
        },
        {
            "fieldname": "rootedops_payroll_payment_method",
            "label": "Payroll Payment Method",
            "fieldtype": "Select",
            "options": PAYMENT_METHOD_OPTIONS,
            "insert_after": "rootedops_payroll_payment_section",
        },
        {
            "fieldname": "rootedops_payroll_payment_active",
            "label": "Payroll Payment Configuration Active",
            "fieldtype": "Check",
            "insert_after": "rootedops_payroll_payment_method",
            "default": "0",
        },
        {
            "fieldname": "rootedops_payroll_payment_effective_date",
            "label": "Payroll Payment Effective Date",
            "fieldtype": "Date",
            "insert_after": "rootedops_payroll_payment_active",
            "description": "Optional first date on which this payment method may be used.",
        },
        {
            "fieldname": "rootedops_payroll_payment_instructions",
            "label": "Payroll Payment Instructions",
            "fieldtype": "Small Text",
            "insert_after": "rootedops_payroll_payment_effective_date",
            "description": (
                "Non-sensitive operational notes only. Do not store ACH routing or account "
                "numbers here; protected ACH fields are intentionally deferred to Issue #6."
            ),
        },
    ],
    "Journal Entry": [
        {
            "fieldname": "rootedops_employee_payroll_payment_section",
            "label": "RootedOps Employee Payroll Payment",
            "fieldtype": "Section Break",
            "insert_after": "user_remark",
            "collapsible": 1,
            "depends_on": "eval:doc.rootedops_payroll_payment_employee",
        },
        {
            "fieldname": "rootedops_payroll_payment_employee",
            "label": "Payroll Payment Employee",
            "fieldtype": "Link",
            "options": "Employee",
            "insert_after": "rootedops_employee_payroll_payment_section",
            "read_only": 1,
            "no_copy": 1,
        },
        {
            "fieldname": "rootedops_payroll_payment_salary_slip",
            "label": "Payroll Payment Salary Slip",
            "fieldtype": "Link",
            "options": "Salary Slip",
            "insert_after": "rootedops_payroll_payment_employee",
            "read_only": 1,
            "no_copy": 1,
        },
        {
            "fieldname": "rootedops_payroll_payment_payroll_entry",
            "label": "Payroll Payment Payroll Entry",
            "fieldtype": "Link",
            "options": "Payroll Entry",
            "insert_after": "rootedops_payroll_payment_salary_slip",
            "read_only": 1,
            "no_copy": 1,
        },
        {
            "fieldname": "rootedops_payroll_payment_method",
            "label": "Payroll Payment Method",
            "fieldtype": "Select",
            "options": PAYMENT_METHOD_OPTIONS,
            "insert_after": "rootedops_payroll_payment_payroll_entry",
            "read_only": 1,
            "no_copy": 1,
        },
        {
            "fieldname": "rootedops_payroll_payment_logical_key",
            "label": "Payroll Payment Logical Key",
            "fieldtype": "Data",
            "insert_after": "rootedops_payroll_payment_method",
            "read_only": 1,
            "no_copy": 1,
            "description": (
                "Stable Salary Slip -> full-net-pay settlement identity shared by all payment attempts."
            ),
        },
        {
            "fieldname": "rootedops_payroll_payment_key",
            "label": "Payroll Payment Attempt Key",
            "fieldtype": "Data",
            "insert_after": "rootedops_payroll_payment_logical_key",
            "read_only": 1,
            "no_copy": 1,
            "unique": 1,
            "description": (
                "Unique identity for one employee-payment JE attempt. Cancelled attempts retain their key."
            ),
        },
        {
            "fieldname": "rootedops_payroll_payment_attempt",
            "label": "Payroll Payment Attempt",
            "fieldtype": "Int",
            "insert_after": "rootedops_payroll_payment_key",
            "read_only": 1,
            "no_copy": 1,
            "default": "0",
            "description": "Sequential attempt number for this Salary Slip payment relationship.",
        },
    ],
    "Payroll Entry": [
        {
            "fieldname": "rootedops_employee_payment_status_section",
            "label": "RootedOps Employee Payment Status",
            "fieldtype": "Section Break",
            "insert_after": "rootedops_payroll_summary",
            "collapsible": 1,
        },
        {
            "fieldname": "rootedops_employee_payment_status_html",
            "label": "Employee Payment Status",
            "fieldtype": "HTML",
            "insert_after": "rootedops_employee_payment_status_section",
        },
    ],
}


def ensure_employee_payment_custom_fields():
    """Install/update employee-payment configuration and lifecycle audit fields."""
    create_custom_fields(EMPLOYEE_PAYMENT_CUSTOM_FIELDS, update=True)
    _backfill_employee_payment_lifecycle_fields()
    frappe.db.commit()


def validate_payment_method(payment_method: str | None, *, required: bool = False) -> str | None:
    """Return a supported method or raise a user-facing validation error."""
    payment_method = (payment_method or "").strip() or None
    if not payment_method:
        if required:
            frappe.throw(_("Payroll Payment Method is required."))
        return None

    if payment_method not in PAYMENT_METHODS:
        frappe.throw(
            _("Unsupported Payroll Payment Method: {0}. Expected one of: {1}").format(
                payment_method,
                ", ".join(PAYMENT_METHODS),
            )
        )
    return payment_method


def payment_configuration_is_effective(configuration: dict, on_date=None) -> bool:
    """Return whether a configuration is active and effective on ``on_date``.

    This helper is intentionally side-effect free so later payment-generation
    code can share one interpretation of the Employee configuration.
    """
    if not cint(configuration.get("active") or 0):
        return False
    if not validate_payment_method(configuration.get("payment_method")):
        return False

    effective_date = configuration.get("effective_date")
    if not effective_date:
        return True

    return getdate(effective_date) <= getdate(on_date)


def get_employee_payment_configuration(employee: str) -> dict:
    """Return non-sensitive payroll-payment configuration for one Employee."""
    if not frappe.db.exists("Employee", employee):
        frappe.throw(_("Employee {0} not found.").format(employee))

    values = frappe.db.get_value(
        "Employee",
        employee,
        [
            "rootedops_payroll_payment_method",
            "rootedops_payroll_payment_active",
            "rootedops_payroll_payment_effective_date",
            "rootedops_payroll_payment_instructions",
        ],
        as_dict=True,
    )

    payment_method = validate_payment_method(values.get("rootedops_payroll_payment_method"))
    return {
        "employee": employee,
        "payment_method": payment_method,
        "active": cint(values.get("rootedops_payroll_payment_active") or 0),
        "effective_date": values.get("rootedops_payroll_payment_effective_date"),
        "instructions": values.get("rootedops_payroll_payment_instructions") or None,
    }


def build_employee_payment_key(salary_slip: str) -> str:
    """Return the stable identity for a full-net-pay Salary Slip settlement."""
    salary_slip = (salary_slip or "").strip()
    if not salary_slip:
        frappe.throw(_("Salary Slip is required to build a payroll payment key."))
    return f"salary-slip:{salary_slip}:full-net-pay"


def build_employee_payment_attempt_key(salary_slip: str, attempt: int) -> str:
    """Return a unique key for one JE attempt while preserving the stable logical key."""
    logical_key = build_employee_payment_key(salary_slip)
    attempt = cint(attempt)
    if attempt < 1:
        frappe.throw(_("Payroll payment attempt must be at least 1."))
    return f"{logical_key}:attempt:{attempt}"


def payment_status_from_docstatus(docstatus: int | None) -> str:
    if docstatus is None:
        return PAYMENT_STATUS_NOT_RECORDED
    docstatus = cint(docstatus)
    if docstatus == 0:
        return PAYMENT_STATUS_DRAFT
    if docstatus == 1:
        return PAYMENT_STATUS_SUBMITTED
    if docstatus == 2:
        return PAYMENT_STATUS_CANCELLED
    return PAYMENT_STATUS_NOT_RECORDED


def _row_value(row, fieldname, default=None):
    if isinstance(row, dict):
        return row.get(fieldname, default)
    return getattr(row, fieldname, default)


def _money(value) -> float:
    return round(float(value or 0), 2)


def assess_employee_payment_journal_entry(je, expected: dict) -> dict:
    """Validate one employee-payment JE against its authoritative Salary Slip plan.

    This intentionally validates the accounting lines in addition to the header
    linkage.  A JE is considered consistent only when the full net-pay amount is
    debited from the expected employee Payroll Payable row and credited to the
    expected checking account, with no additional debit/credit amount elsewhere.
    """
    errors = []
    net_pay = _money(expected.get("net_pay"))

    header_expectations = (
        ("company", expected.get("company"), "Company"),
        ("rootedops_payroll_payment_employee", expected.get("employee"), "Employee"),
        (
            "rootedops_payroll_payment_salary_slip",
            expected.get("salary_slip"),
            "Salary Slip",
        ),
        (
            "rootedops_payroll_payment_payroll_entry",
            expected.get("payroll_entry"),
            "Payroll Entry",
        ),
    )
    for fieldname, expected_value, label in header_expectations:
        if expected_value and _row_value(je, fieldname) != expected_value:
            errors.append(
                _("{0} link is {1}, expected {2}.").format(
                    label,
                    _row_value(je, fieldname) or _("blank"),
                    expected_value,
                )
            )

    rows = list(_row_value(je, "accounts", []) or [])
    total_debit = _money(
        sum(_money(_row_value(row, "debit_in_account_currency")) for row in rows)
    )
    total_credit = _money(
        sum(_money(_row_value(row, "credit_in_account_currency")) for row in rows)
    )

    payable_debit = _money(
        sum(
            _money(_row_value(row, "debit_in_account_currency"))
            for row in rows
            if _row_value(row, "account") == expected.get("payroll_payable_account")
            and _row_value(row, "party_type") == "Employee"
            and _row_value(row, "party") == expected.get("employee")
        )
    )
    checking_credit = _money(
        sum(
            _money(_row_value(row, "credit_in_account_currency"))
            for row in rows
            if _row_value(row, "account") == expected.get("checking_bank_account")
        )
    )

    if total_debit != net_pay:
        errors.append(
            _("Total debit is {0}, expected Salary Slip net pay {1}.").format(
                total_debit, net_pay
            )
        )
    if total_credit != net_pay:
        errors.append(
            _("Total credit is {0}, expected Salary Slip net pay {1}.").format(
                total_credit, net_pay
            )
        )
    if payable_debit != net_pay:
        errors.append(
            _("Payroll Payable debit is {0}, expected {1}.").format(payable_debit, net_pay)
        )
    if checking_credit != net_pay:
        errors.append(
            _("Checking-account credit is {0}, expected {1}.").format(
                checking_credit, net_pay
            )
        )

    return {
        "consistent": not errors,
        "status": PAYMENT_ACCOUNTING_MATCH if not errors else PAYMENT_ACCOUNTING_MISMATCH,
        "errors": errors,
        "expected_net_pay": net_pay,
        "total_debit": total_debit,
        "total_credit": total_credit,
        "payroll_payable_debit": payable_debit,
        "checking_credit": checking_credit,
    }


def summarize_employee_payment_statuses(statuses) -> dict:
    """Return batch-level settlement totals for Payroll Entry UI/reconciliation."""
    statuses = list(statuses or [])
    positive = [row for row in statuses if _money(row.get("net_pay")) > 0]

    expected_total = _money(sum(_money(row.get("net_pay")) for row in positive))
    draft_total = _money(
        sum(_money(row.get("net_pay")) for row in positive if row.get("status") == PAYMENT_STATUS_DRAFT)
    )
    submitted_total = _money(
        sum(
            _money(row.get("net_pay"))
            for row in positive
            if row.get("status") == PAYMENT_STATUS_SUBMITTED
        )
    )
    active_expected_total = _money(draft_total + submitted_total)
    outstanding_total = _money(max(expected_total - active_expected_total, 0))
    conflict_count = sum(1 for row in positive if row.get("status") == PAYMENT_STATUS_CONFLICT)
    mismatch_count = sum(1 for row in positive if row.get("accounting_consistent") is False)
    not_recorded_count = sum(
        1 for row in positive if row.get("status") == PAYMENT_STATUS_NOT_RECORDED
    )
    cancelled_count = sum(1 for row in positive if row.get("status") == PAYMENT_STATUS_CANCELLED)

    return {
        "employee_count": len(statuses),
        "positive_net_pay_employee_count": len(positive),
        "expected_net_pay_total": expected_total,
        "draft_payment_total": draft_total,
        "submitted_payment_total": submitted_total,
        "active_payment_total": active_expected_total,
        "outstanding_net_pay_total": outstanding_total,
        "not_recorded_count": not_recorded_count,
        "cancelled_count": cancelled_count,
        "conflict_count": conflict_count,
        "accounting_mismatch_count": mismatch_count,
        "all_positive_net_pay_recorded": bool(positive)
        and not_recorded_count == 0
        and cancelled_count == 0
        and conflict_count == 0,
        "all_accounting_consistent": conflict_count == 0 and mismatch_count == 0,
    }


def _get_payment_journal_entry_history(salary_slip: str):
    """Return all employee-payment JEs for a Salary Slip in creation order."""
    return frappe.get_all(
        "Journal Entry",
        filters={"rootedops_payroll_payment_salary_slip": salary_slip},
        fields=[
            "name",
            "docstatus",
            "creation",
            "modified",
            "rootedops_payroll_payment_method",
            "rootedops_payroll_payment_logical_key",
            "rootedops_payroll_payment_key",
            "rootedops_payroll_payment_attempt",
        ],
        order_by="creation asc, name asc",
    )


def summarize_payment_history(salary_slip: str, rows) -> dict:
    """Summarize the live payment lifecycle for one Salary Slip.

    Draft/submitted JEs are active settlement records and block regeneration.
    Cancelled JEs remain audit history but make the Salary Slip eligible for a new
    attempt. More than one active JE is surfaced as a conflict instead of being
    silently resolved.
    """
    rows = list(rows or [])
    active = [row for row in rows if cint(row.get("docstatus")) in (0, 1)]
    cancelled = [row for row in rows if cint(row.get("docstatus")) == 2]

    if len(active) > 1:
        status = PAYMENT_STATUS_CONFLICT
        current = active[-1]
    elif active:
        current = active[0]
        status = payment_status_from_docstatus(current.get("docstatus"))
    elif cancelled:
        current = cancelled[-1]
        status = PAYMENT_STATUS_CANCELLED
    else:
        current = None
        status = PAYMENT_STATUS_NOT_RECORDED

    attempts = []
    for index, row in enumerate(rows, start=1):
        attempts.append(
            {
                "journal_entry": row.get("name"),
                "docstatus": cint(row.get("docstatus")),
                "status": payment_status_from_docstatus(row.get("docstatus")),
                "payment_method": row.get("rootedops_payroll_payment_method"),
                "payment_key": row.get("rootedops_payroll_payment_key"),
                "attempt": cint(row.get("rootedops_payroll_payment_attempt")) or index,
            }
        )

    return {
        "salary_slip": salary_slip,
        "status": status,
        "journal_entry": current.get("name") if current else None,
        "docstatus": cint(current.get("docstatus")) if current else None,
        "payment_method": current.get("rootedops_payroll_payment_method") if current else None,
        "active_count": len(active),
        "attempt_count": len(rows),
        "next_attempt": len(rows) + 1,
        "can_regenerate": not active,
        "attempts": attempts,
    }


def resolve_salary_slip_payment_status(salary_slip: str) -> dict:
    return summarize_payment_history(salary_slip, _get_payment_journal_entry_history(salary_slip))


def _backfill_employee_payment_lifecycle_fields():
    """Backfill Phase-2 JEs without changing accounting or legacy attempt keys."""
    if not frappe.db.has_column("Journal Entry", "rootedops_payroll_payment_logical_key"):
        return

    rows = frappe.get_all(
        "Journal Entry",
        filters={"rootedops_payroll_payment_salary_slip": ["is", "set"]},
        fields=[
            "name",
            "rootedops_payroll_payment_salary_slip",
            "rootedops_payroll_payment_logical_key",
            "rootedops_payroll_payment_attempt",
            "creation",
        ],
        order_by="rootedops_payroll_payment_salary_slip asc, creation asc, name asc",
    )

    attempt_by_slip = {}
    for row in rows:
        slip = row.get("rootedops_payroll_payment_salary_slip")
        if not slip:
            continue
        attempt_by_slip[slip] = attempt_by_slip.get(slip, 0) + 1
        updates = {}
        if not row.get("rootedops_payroll_payment_logical_key"):
            updates["rootedops_payroll_payment_logical_key"] = build_employee_payment_key(slip)
        if not cint(row.get("rootedops_payroll_payment_attempt")):
            updates["rootedops_payroll_payment_attempt"] = attempt_by_slip[slip]
        if updates:
            frappe.db.set_value("Journal Entry", row.get("name"), updates, update_modified=False)


def preflight_employee_payroll_payments(
    payroll_results,
    *,
    payroll_entry: str,
    company: str,
    posting_date,
):
    """Validate a complete employee-payment batch before any JE is inserted.

    Phase 3 preserves the all-or-nothing draft batch. Every
    positive-net-pay Salary Slip must be submitted, belong to the requested
    Payroll Entry/company, have an effective Employee payment configuration,
    resolve the payroll payable and checking accounts, and have no existing
    active employee-payment JE.
    """
    from rootedops_payroll.services.payroll_engine import (
        get_default_checking_bank_gl_account,
        get_payroll_account_map,
    )

    if not payroll_results:
        frappe.throw(_("No submitted Salary Slips are available for employee payment."))

    checking_bank_account = get_default_checking_bank_gl_account(company)
    if not checking_bank_account:
        frappe.throw(_("No default checking Bank GL Account could be resolved for {0}.").format(company))

    plans = []
    zero_net_pay = []
    seen_slips = set()

    for result in payroll_results:
        slip_name = (result.get("slip_name") or "").strip()
        if not slip_name:
            frappe.throw(_("Payroll result is missing its Salary Slip name."))
        if slip_name in seen_slips:
            frappe.throw(_("Salary Slip {0} appears more than once in the payment batch.").format(slip_name))
        seen_slips.add(slip_name)

        slip = frappe.get_doc("Salary Slip", slip_name)
        if slip.docstatus != 1:
            frappe.throw(_("Salary Slip {0} must be submitted before payment accounting is created.").format(slip_name))
        if slip.company != company:
            frappe.throw(_("Salary Slip {0} belongs to {1}, not {2}.").format(slip_name, slip.company, company))
        if result.get("employee") and result.get("employee") != slip.employee:
            frappe.throw(_("Salary Slip {0} employee does not match the payroll result.").format(slip_name))

        net_pay = round(float(slip.net_pay or 0), 2)
        if net_pay < 0:
            frappe.throw(_("Salary Slip {0} has negative net pay and cannot be settled by this workflow.").format(slip_name))
        if net_pay == 0:
            zero_net_pay.append(slip_name)
            continue

        configuration = get_employee_payment_configuration(slip.employee)
        payment_method = validate_payment_method(configuration.get("payment_method"), required=True)
        if not payment_configuration_is_effective(configuration, posting_date):
            frappe.throw(
                _("Employee {0} does not have an active payroll payment configuration effective on {1}.").format(
                    slip.employee, posting_date
                )
            )

        payment_status = resolve_salary_slip_payment_status(slip_name)
        if payment_status["active_count"] > 1:
            frappe.throw(
                _("Salary Slip {0} has multiple active employee payment Journal Entries. Resolve the conflict before continuing.").format(
                    slip_name
                )
            )
        if not payment_status["can_regenerate"]:
            frappe.throw(
                _("Salary Slip {0} already has {1}: {2}.").format(
                    slip_name, payment_status["status"], payment_status.get("journal_entry")
                )
            )

        account_map = get_payroll_account_map(
            company,
            payroll_payable_account=getattr(slip, "payroll_payable_account", None),
            overrides=None,
        )
        payroll_payable_account = account_map.get("payroll_payable_account")
        if not payroll_payable_account:
            frappe.throw(_("Could not resolve Payroll Payable for Salary Slip {0}.").format(slip_name))

        plans.append(
            {
                "employee": slip.employee,
                "employee_name": getattr(slip, "employee_name", None) or slip.employee,
                "salary_slip": slip.name,
                "payroll_entry": payroll_entry,
                "company": company,
                "posting_date": posting_date,
                "net_pay": net_pay,
                "payment_method": payment_method,
                "logical_key": build_employee_payment_key(slip.name),
                "payment_attempt": payment_status["next_attempt"],
                "payment_key": build_employee_payment_attempt_key(
                    slip.name, payment_status["next_attempt"]
                ),
                "prior_payment_status": payment_status["status"],
                "payroll_payable_account": payroll_payable_account,
                "checking_bank_account": checking_bank_account,
                "cost_center": getattr(slip, "cost_center", None),
            }
        )

    if not plans and not zero_net_pay:
        frappe.throw(_("No employee payroll payments were eligible for creation."))

    return {
        "plans": plans,
        "zero_net_pay_salary_slips": zero_net_pay,
        "checking_bank_account": checking_bank_account,
        "total_net_pay": round(sum(plan["net_pay"] for plan in plans), 2),
    }


def _employee_payment_journal_entry_doc(plan):
    debit = {
        "account": plan["payroll_payable_account"],
        "party_type": "Employee",
        "party": plan["employee"],
        "debit_in_account_currency": plan["net_pay"],
        "credit_in_account_currency": 0,
        "user_remark": f"Clear payroll payable for {plan['salary_slip']}",
    }
    credit = {
        "account": plan["checking_bank_account"],
        "debit_in_account_currency": 0,
        "credit_in_account_currency": plan["net_pay"],
        "user_remark": f"Payroll payment to {plan['employee']} via {plan['payment_method']}",
    }
    if plan.get("cost_center"):
        debit["cost_center"] = plan["cost_center"]
        credit["cost_center"] = plan["cost_center"]

    return frappe.get_doc(
        {
            "doctype": "Journal Entry",
            "voucher_type": "Bank Entry",
            "company": plan["company"],
            "posting_date": plan["posting_date"],
            "user_remark": (
                f"Payroll payment for {plan['employee_name']}; "
                f"Salary Slip {plan['salary_slip']}; Payroll Entry {plan['payroll_entry']}; "
                f"payment method {plan['payment_method']}; payment attempt {plan['payment_attempt']}."
            ),
            "rootedops_payroll_payment_employee": plan["employee"],
            "rootedops_payroll_payment_salary_slip": plan["salary_slip"],
            "rootedops_payroll_payment_payroll_entry": plan["payroll_entry"],
            "rootedops_payroll_payment_method": plan["payment_method"],
            "rootedops_payroll_payment_logical_key": plan["logical_key"],
            "rootedops_payroll_payment_key": plan["payment_key"],
            "rootedops_payroll_payment_attempt": plan["payment_attempt"],
            "accounts": [debit, credit],
        }
    )


def _expected_payment_plan_from_result(
    result,
    *,
    payroll_entry: str,
    company: str,
    checking_bank_account: str,
):
    """Resolve authoritative accounting expectations for an existing Salary Slip."""
    from rootedops_payroll.services.payroll_engine import get_payroll_account_map

    slip_name = (result.get("slip_name") or "").strip()
    if not slip_name:
        frappe.throw(_("Payroll result is missing its Salary Slip name."))

    slip = frappe.get_doc("Salary Slip", slip_name)
    account_map = get_payroll_account_map(
        company,
        payroll_payable_account=getattr(slip, "payroll_payable_account", None),
        overrides=None,
    )
    payroll_payable_account = account_map.get("payroll_payable_account")
    if not payroll_payable_account:
        frappe.throw(_("Could not resolve Payroll Payable for Salary Slip {0}.").format(slip_name))

    return {
        "employee": slip.employee,
        "salary_slip": slip.name,
        "payroll_entry": payroll_entry,
        "company": company,
        "net_pay": _money(slip.net_pay),
        "payroll_payable_account": payroll_payable_account,
        "checking_bank_account": checking_bank_account,
    }


def create_employee_payroll_payment_drafts(
    payroll_results,
    *,
    payroll_entry: str,
    company: str,
    posting_date,
):
    """Create one draft Bank Entry JE per positive-net-pay submitted Salary Slip.

    No explicit commit occurs here.  Frappe's request transaction owns the
    commit, so an insert failure rolls back the whole batch rather than leaving
    only some employees with payment JEs.
    """
    preflight = preflight_employee_payroll_payments(
        payroll_results,
        payroll_entry=payroll_entry,
        company=company,
        posting_date=posting_date,
    )

    created = []
    for plan in preflight["plans"]:
        je = _employee_payment_journal_entry_doc(plan)
        je.insert(ignore_permissions=True)
        accounting = assess_employee_payment_journal_entry(je, plan)
        if not accounting["consistent"]:
            frappe.throw(
                _("Employee payment Journal Entry {0} failed accounting validation: {1}").format(
                    je.name,
                    " ".join(accounting["errors"]),
                )
            )
        created.append(
            {
                "employee": plan["employee"],
                "employee_name": plan["employee_name"],
                "salary_slip": plan["salary_slip"],
                "payment_method": plan["payment_method"],
                "net_pay": plan["net_pay"],
                "journal_entry": je.name,
                "docstatus": je.docstatus,
                "status": payment_status_from_docstatus(je.docstatus),
                "payment_attempt": plan["payment_attempt"],
                "prior_payment_status": plan["prior_payment_status"],
                "accounting_consistent": accounting["consistent"],
                "accounting_status": accounting["status"],
                "accounting_total": accounting["checking_credit"],
            }
        )

    created_total = _money(sum(row["accounting_total"] for row in created))
    if created_total != preflight["total_net_pay"]:
        frappe.throw(_("Employee payment Journal Entry total did not reconcile to Salary Slip net pay."))

    return {
        "journal_entries": created,
        "employee_count": len(created),
        "total_net_pay": created_total,
        "checking_bank_account": preflight["checking_bank_account"],
        "zero_net_pay_salary_slips": preflight["zero_net_pay_salary_slips"],
    }


def get_employee_payroll_payment_statuses(
    payroll_results,
    *,
    payroll_entry: str | None = None,
    company: str | None = None,
) -> list[dict]:
    """Return lifecycle plus accounting-consistency status for Salary Slips."""
    checking_bank_account = None
    if payroll_entry and company:
        from rootedops_payroll.services.payroll_engine import get_default_checking_bank_gl_account

        checking_bank_account = get_default_checking_bank_gl_account(company)

    statuses = []
    for result in payroll_results or []:
        slip_name = (result.get("slip_name") or "").strip()
        if not slip_name:
            continue
        status = resolve_salary_slip_payment_status(slip_name)
        status.update(
            {
                "employee": result.get("employee"),
                "employee_name": result.get("employee_name") or result.get("employee"),
                "net_pay": round(float(result.get("net_pay") or 0), 2),
            }
        )

        if status.get("journal_entry") and payroll_entry and company and checking_bank_account:
            expected = _expected_payment_plan_from_result(
                result,
                payroll_entry=payroll_entry,
                company=company,
                checking_bank_account=checking_bank_account,
            )
            je = frappe.get_doc("Journal Entry", status["journal_entry"])
            accounting = assess_employee_payment_journal_entry(je, expected)
            status.update(
                {
                    "accounting_consistent": accounting["consistent"],
                    "accounting_status": accounting["status"],
                    "accounting_errors": accounting["errors"],
                    "recorded_amount": accounting["checking_credit"],
                }
            )
        else:
            status.update(
                {
                    "accounting_consistent": None,
                    "accounting_status": PAYMENT_ACCOUNTING_NOT_RECORDED,
                    "accounting_errors": [],
                    "recorded_amount": 0,
                }
            )
        statuses.append(status)
    return statuses
