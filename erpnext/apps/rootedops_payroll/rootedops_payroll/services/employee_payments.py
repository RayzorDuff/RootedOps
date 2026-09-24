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
            "fieldname": "rootedops_payroll_payment_key",
            "label": "Payroll Payment Key",
            "fieldtype": "Data",
            "insert_after": "rootedops_payroll_payment_method",
            "read_only": 1,
            "no_copy": 1,
            "unique": 1,
            "description": (
                "Reserved stable identity for the future Salary Slip -> employee payment JE relationship."
            ),
        },
    ],
}


def ensure_employee_payment_custom_fields():
    """Install/update Phase-1 payment configuration and audit fields."""
    create_custom_fields(EMPLOYEE_PAYMENT_CUSTOM_FIELDS, update=True)
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


def _get_active_payment_journal_entry(salary_slip: str):
    """Return an existing non-cancelled employee-payment JE for a Salary Slip."""
    rows = frappe.get_all(
        "Journal Entry",
        filters={
            "rootedops_payroll_payment_salary_slip": salary_slip,
            "docstatus": ["!=", 2],
        },
        fields=["name", "docstatus"],
        order_by="creation asc",
        limit=1,
    )
    return rows[0] if rows else None


def preflight_employee_payroll_payments(
    payroll_results,
    *,
    payroll_entry: str,
    company: str,
    posting_date,
):
    """Validate a complete employee-payment batch before any JE is inserted.

    Phase 2 intentionally creates an all-or-nothing draft batch.  Every
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

        existing = _get_active_payment_journal_entry(slip_name)
        if existing:
            frappe.throw(
                _("Salary Slip {0} already has an active employee payment Journal Entry: {1}.").format(
                    slip_name, existing.get("name")
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
                "payment_key": build_employee_payment_key(slip.name),
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
                f"payment method {plan['payment_method']}."
            ),
            "rootedops_payroll_payment_employee": plan["employee"],
            "rootedops_payroll_payment_salary_slip": plan["salary_slip"],
            "rootedops_payroll_payment_payroll_entry": plan["payroll_entry"],
            "rootedops_payroll_payment_method": plan["payment_method"],
            "rootedops_payroll_payment_key": plan["payment_key"],
            "accounts": [debit, credit],
        }
    )


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
        created.append(
            {
                "employee": plan["employee"],
                "employee_name": plan["employee_name"],
                "salary_slip": plan["salary_slip"],
                "payment_method": plan["payment_method"],
                "net_pay": plan["net_pay"],
                "journal_entry": je.name,
                "docstatus": je.docstatus,
            }
        )

    created_total = round(sum(row["net_pay"] for row in created), 2)
    if created_total != preflight["total_net_pay"]:
        frappe.throw(_("Employee payment Journal Entry total did not reconcile to Salary Slip net pay."))

    return {
        "journal_entries": created,
        "employee_count": len(created),
        "total_net_pay": created_total,
        "checking_bank_account": preflight["checking_bank_account"],
        "zero_net_pay_salary_slips": preflight["zero_net_pay_salary_slips"],
    }
