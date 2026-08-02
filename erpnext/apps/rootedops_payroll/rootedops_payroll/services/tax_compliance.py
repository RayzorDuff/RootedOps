from __future__ import annotations

from collections import defaultdict

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils import cint, flt, getdate

from rootedops_payroll.services.payroll_engine import (
    get_default_checking_bank_gl_account,
    get_payroll_account_map,
    get_withholding_bank_gl_account,
)
from rootedops_payroll.rootedops_payroll.report.quarterly_payroll_tax_report.quarterly_payroll_tax_report import (
    get_quarter_tax_totals,
)


TAX_TYPES = (
    "Federal Payroll Tax",
    "Colorado Withholding",
    "Colorado UI",
    "Colorado FAMLI",
)

JOURNAL_ENTRY_TAX_PAYMENT_CUSTOM_FIELDS = {
    "Journal Entry": [
        {"fieldname": "rootedops_tax_payment_section", "label": "RootedOps Payroll Tax Payment", "fieldtype": "Section Break", "insert_after": "user_remark", "collapsible": 1},
        {"fieldname": "rootedops_tax_type", "label": "Payroll Tax Type", "fieldtype": "Select", "options": "\nFederal Payroll Tax\nColorado Withholding\nColorado UI\nColorado FAMLI", "insert_after": "rootedops_tax_payment_section", "read_only": 1},
        {"fieldname": "rootedops_tax_year", "label": "Tax Year", "fieldtype": "Int", "insert_after": "rootedops_tax_type", "read_only": 1},
        {"fieldname": "rootedops_tax_quarter", "label": "Tax Quarter", "fieldtype": "Select", "options": "\nQ1\nQ2\nQ3\nQ4", "insert_after": "rootedops_tax_year", "read_only": 1},
        {"fieldname": "rootedops_tax_payment_key", "label": "Tax Payment Key", "fieldtype": "Data", "insert_after": "rootedops_tax_quarter", "read_only": 1, "unique": 1, "no_copy": 1},
    ]
}


def ensure_tax_payment_custom_fields():
    create_custom_fields(JOURNAL_ENTRY_TAX_PAYMENT_CUSTOM_FIELDS, update=True)
    frappe.db.commit()


def _payment_key(company, year, quarter, tax_type):
    return f"{company}|{cint(year)}|{quarter}|{tax_type}"


def _liability_parts(totals, account_map):
    return {
        "Federal Payroll Tax": [
            (account_map["federal_withholding_payable_account"], flt(totals.get("federal_withholding"), 2)),
            (account_map["social_security_payable_account"], flt(totals.get("social_security_employee"), 2) + flt(totals.get("social_security_employer"), 2)),
            (account_map["medicare_payable_account"], flt(totals.get("medicare_employee"), 2) + flt(totals.get("medicare_employer"), 2)),
        ],
        "Colorado Withholding": [
            (account_map["colorado_withholding_payable_account"], flt(totals.get("colorado_withholding"), 2)),
        ],
        "Colorado UI": [
            (account_map["payroll_tax_payable_account"], flt(totals.get("colorado_ui_employer"), 2)),
        ],
        "Colorado FAMLI": [
            (account_map["payroll_tax_payable_account"], flt(totals.get("colorado_famli_total_remittance"), 2)),
        ],
    }


def _combine_parts(parts):
    combined = defaultdict(float)
    missing = []
    for account, amount in parts:
        if not amount:
            continue
        if not account:
            missing.append(account)
            continue
        combined[account] += amount
    return [(account, flt(amount, 2)) for account, amount in combined.items()], missing


def get_tax_reconciliation(company, year, quarter):
    totals = get_quarter_tax_totals(company, year, quarter)
    account_map = get_payroll_account_map(company)
    parts_by_type = _liability_parts(totals, account_map)

    payments = frappe.get_all(
        "Journal Entry",
        filters={
            "company": company,
            "rootedops_tax_year": cint(year),
            "rootedops_tax_quarter": quarter,
            "rootedops_tax_type": ["in", list(TAX_TYPES)],
            "docstatus": ["in", [0, 1]],
        },
        fields=["name", "rootedops_tax_type", "docstatus", "posting_date"],
        order_by="posting_date asc, creation asc",
    )
    payment_names = [payment.name for payment in payments]
    payment_lines = frappe.get_all(
        "Journal Entry Account",
        filters={"parent": ["in", payment_names], "debit": [">", 0]},
        fields=["parent", "account", "debit"],
    ) if payment_names else []
    lines_by_payment = defaultdict(list)
    for line in payment_lines:
        lines_by_payment[line.parent].append(line)

    by_type = defaultdict(lambda: {
        "draft": 0.0,
        "paid": 0.0,
        "draft_entries": [],
        "submitted_entries": [],
    })
    for payment in payments:
        bucket = by_type[payment.rootedops_tax_type]
        key = "paid" if payment.docstatus == 1 else "draft"
        expected_accounts = {
            account
            for account, amount in parts_by_type[payment.rootedops_tax_type]
            if account and amount
        }
        cleared = sum(
            flt(line.debit, 2)
            for line in lines_by_payment[payment.name]
            if line.account in expected_accounts
        )
        bucket[key] += flt(cleared, 2)
        entries_key = "submitted_entries" if payment.docstatus == 1 else "draft_entries"
        bucket[entries_key].append(payment.name)

    rows = []
    for tax_type in TAX_TYPES:
        parts, missing = _combine_parts(parts_by_type[tax_type])
        accrued = flt(sum(amount for _account, amount in parts), 2)
        payment = by_type[tax_type]
        paid = flt(payment["paid"], 2)
        draft = flt(payment["draft"], 2)
        outstanding = flt(accrued - paid, 2)
        projected_outstanding = flt(outstanding - draft, 2)
        rows.append({
            "tax_type": tax_type,
            "accrued": accrued,
            "draft_payments": draft,
            "paid": paid,
            "outstanding": outstanding,
            "projected_outstanding": projected_outstanding,
            "draft_entries": ", ".join(payment["draft_entries"]),
            "submitted_entries": ", ".join(payment["submitted_entries"]),
            "payable_accounts": ", ".join(account for account, _amount in parts),
            "missing_accounts": missing,
        })
    return rows


@frappe.whitelist()
def link_existing_tax_payment(company, year, quarter, tax_type, journal_entry):
    frappe.has_permission("Journal Entry", "write", throw=True)
    year = cint(year)
    if quarter not in ("Q1", "Q2", "Q3", "Q4"):
        frappe.throw(_("Select a valid quarter."))
    if tax_type not in TAX_TYPES:
        frappe.throw(_("Select a valid payroll tax type."))

    je = frappe.get_doc("Journal Entry", journal_entry)
    if je.company != company:
        frappe.throw(_("Journal Entry {0} belongs to {1}, not {2}.").format(je.name, je.company, company))
    if je.docstatus == 2:
        frappe.throw(_("Cancelled Journal Entries cannot be linked as tax payments."))

    key = _payment_key(company, year, quarter, tax_type)
    if je.rootedops_tax_payment_key and je.rootedops_tax_payment_key != key:
        frappe.throw(
            _("Journal Entry {0} is already linked to a different payroll tax obligation.").format(je.name)
        )
    existing = frappe.db.get_value(
        "Journal Entry",
        {
            "rootedops_tax_payment_key": key,
            "docstatus": ["!=", 2],
            "name": ["!=", je.name],
        },
        "name",
    )
    if existing:
        frappe.throw(_("A non-cancelled payment Journal Entry already exists for this obligation: {0}").format(existing))

    totals = get_quarter_tax_totals(company, year, quarter)
    account_map = get_payroll_account_map(company)
    parts, missing = _combine_parts(_liability_parts(totals, account_map)[tax_type])
    if missing or not parts:
        frappe.throw(_("The liability account mapping for {0} is incomplete or the calculated liability is zero.").format(tax_type))

    expected_accounts = {account for account, _amount in parts}
    cleared = flt(sum(
        flt(row.debit_in_account_currency, 2)
        for row in je.accounts
        if row.account in expected_accounts
    ), 2)
    if cleared <= 0:
        frappe.throw(
            _("Journal Entry {0} does not debit the expected liability account(s): {1}").format(
                je.name,
                ", ".join(sorted(expected_accounts)),
            )
        )

    je.db_set({
        "rootedops_tax_type": tax_type,
        "rootedops_tax_year": year,
        "rootedops_tax_quarter": quarter,
        "rootedops_tax_payment_key": key,
    })
    return {
        "journal_entry": je.name,
        "amount": cleared,
        "status": "Submitted" if je.docstatus == 1 else "Draft",
    }


@frappe.whitelist()
def create_tax_payment_draft(company, year, quarter, tax_type, posting_date, reference_no):
    frappe.has_permission("Journal Entry", "create", throw=True)
    year = cint(year)
    if quarter not in ("Q1", "Q2", "Q3", "Q4"):
        frappe.throw(_("Select a valid quarter."))
    if tax_type not in TAX_TYPES:
        frappe.throw(_("Select a valid payroll tax type."))
    if not reference_no:
        frappe.throw(_("Payment reference is required."))

    key = _payment_key(company, year, quarter, tax_type)
    existing = frappe.db.get_value(
        "Journal Entry",
        {"rootedops_tax_payment_key": key, "docstatus": ["!=", 2]},
        "name",
    )
    if existing:
        frappe.throw(_("A non-cancelled payment Journal Entry already exists for this obligation: {0}").format(existing))

    totals = get_quarter_tax_totals(company, year, quarter)
    account_map = get_payroll_account_map(company)
    parts, missing = _combine_parts(_liability_parts(totals, account_map)[tax_type])
    if missing or not parts:
        frappe.throw(_("The liability account mapping for {0} is incomplete or the calculated liability is zero.").format(tax_type))

    bank_account = (
        get_withholding_bank_gl_account(company)
        or get_default_checking_bank_gl_account(company)
    )
    if not bank_account:
        frappe.throw(_("No company bank GL account could be resolved."))

    amount = flt(sum(value for _account, value in parts), 2)
    accounts = [
        {"account": account, "debit_in_account_currency": value}
        for account, value in parts
    ]
    accounts.append({"account": bank_account, "credit_in_account_currency": amount})

    je = frappe.get_doc({
        "doctype": "Journal Entry",
        "voucher_type": "Bank Entry",
        "company": company,
        "posting_date": getdate(posting_date),
        "cheque_no": reference_no,
        "cheque_date": getdate(posting_date),
        "user_remark": f"{tax_type} payment for {quarter} {year}. Reference {reference_no}.",
        "rootedops_tax_type": tax_type,
        "rootedops_tax_year": year,
        "rootedops_tax_quarter": quarter,
        "rootedops_tax_payment_key": key,
        "accounts": accounts,
    })
    je.insert()
    return {"journal_entry": je.name, "amount": amount, "bank_account": bank_account}
