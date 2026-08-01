import frappe
from frappe import _

from rootedops_payroll.services.tax_compliance import get_tax_reconciliation


def execute(filters=None):
    filters = frappe._dict(filters or {})
    if not filters.company:
        frappe.throw(_("Company is required."))
    rows = get_tax_reconciliation(filters.company, filters.year, filters.quarter)
    return get_columns(), rows, None, get_summary(rows)


def get_columns():
    return [
        {"fieldname": "tax_type", "label": _("Tax Type"), "fieldtype": "Data", "width": 190},
        {"fieldname": "accrued", "label": _("Accrued"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "draft_payments", "label": _("Draft Payments"), "fieldtype": "Currency", "width": 130},
        {"fieldname": "paid", "label": _("Submitted Payments"), "fieldtype": "Currency", "width": 145},
        {"fieldname": "outstanding", "label": _("Outstanding"), "fieldtype": "Currency", "width": 125},
        {"fieldname": "payable_accounts", "label": _("Payable Accounts"), "fieldtype": "Data", "width": 230},
        {"fieldname": "payment_entries", "label": _("Payment Entries"), "fieldtype": "Data", "width": 220},
    ]


def get_summary(rows):
    return [
        {"value": sum(row["accrued"] for row in rows), "label": _("Total Accrued"), "datatype": "Currency", "indicator": "Blue"},
        {"value": sum(row["paid"] for row in rows), "label": _("Submitted Payments"), "datatype": "Currency", "indicator": "Green"},
        {"value": sum(row["outstanding"] for row in rows), "label": _("Outstanding"), "datatype": "Currency", "indicator": "Orange"},
    ]
