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
