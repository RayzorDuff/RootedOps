"""Phase E payroll-to-NACHA export orchestration and audit boundary."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import frappe
from frappe import _
from frappe.utils import cint, getdate, now_datetime

from rootedops_payroll.api.payroll_entry_actions import (
    _build_payroll_result_from_existing_slip,
    _get_employees_for_payroll_entry,
    _get_payroll_entry_context,
    _get_salary_slips_for_payroll_entry,
)
from rootedops_payroll.services.employee_payments import (
    PAYMENT_METHOD_ACH,
    get_employee_ach_credentials_for_export,
)
from rootedops_payroll.services.nacha_export_core import build_payroll_ach_export
from rootedops_payroll.services.nacha_file import ACHCredit, NACHAProfile
from rootedops_payroll.services.nacha_profile import get_nacha_profile_configuration


def _require_submitted_payroll_entry(pe):
    if int(pe.docstatus or 0) != 1:
        frappe.throw(_("Payroll Entry must be submitted/finalized before NACHA export."))


def _parse_effective_date(value):
    try:
        return getdate(value)
    except Exception:
        frappe.throw(_("Effective ACH Date must be a valid date."))


def _next_export_version(payroll_entry: str) -> int:
    rows = frappe.get_all(
        "RootedOps NACHA Export",
        filters={"payroll_entry": payroll_entry},
        pluck="export_version",
    )
    return max([cint(v) for v in rows] or [0]) + 1


def _profile_to_formatter(profile: dict, effective_date) -> NACHAProfile:
    return NACHAProfile(
        immediate_destination=profile["immediate_destination"],
        immediate_origin=profile["immediate_origin"],
        destination_name=profile["immediate_destination_name"],
        origin_name=profile["immediate_origin_name"],
        company_name=profile["batch_company_name"],
        company_id=profile["company_id"],
        odfi_identification=profile["originating_dfi_identification"],
        effective_entry_date=effective_date.strftime("%y%m%d"),
        reference_code=profile.get("reference_code") or "",
        balance_mode=(profile.get("balance_mode") or "").lower(),
    )


def build_payroll_export_plan(payroll_entry_name: str, profile_name: str, effective_date):
    pe, ctx = _get_payroll_entry_context(payroll_entry_name)
    _require_submitted_payroll_entry(pe)
    effective_date = _parse_effective_date(effective_date)

    profile = get_nacha_profile_configuration(profile_name)
    if profile["company"] != ctx["company"]:
        frappe.throw(_("NACHA Profile company does not match the Payroll Entry company."))
    if not profile["enabled"]:
        frappe.throw(_("NACHA Profile must be enabled before NACHA export."))
    if profile["configuration_status"] != "Ready":
        frappe.throw(_("NACHA Profile is not ready for export."))
    if (profile.get("balance_mode") or "") != "Unbalanced":
        frappe.throw(_("Phase E supports only a confirmed Unbalanced NACHA Profile."))

    employees = _get_employees_for_payroll_entry(pe, ctx)
    slips = _get_salary_slips_for_payroll_entry(employees, ctx)
    slips = [row for row in slips if int(row.get("docstatus") or 0) == 1]
    if not slips:
        frappe.throw(_("No submitted Salary Slips were found for this Payroll Entry."))

    seen_employees = set()
    entries = []
    excluded = []
    total_net_pay = Decimal("0.00")

    for row in slips:
        slip = frappe.get_doc("Salary Slip", row["name"])
        employee = row["employee"]
        if employee in seen_employees:
            frappe.throw(_("Employee {0} appears more than once in the payroll export.").format(employee))
        seen_employees.add(employee)
        net_pay = Decimal(str(slip.net_pay or 0)).quantize(Decimal("0.01"))
        total_net_pay += net_pay
        payment_method = frappe.db.get_value("Employee", employee, "rootedops_payroll_payment_method")
        if payment_method != PAYMENT_METHOD_ACH:
            excluded.append({
                "employee": employee,
                "employee_name": slip.employee_name,
                "salary_slip": slip.name,
                "payment_method": payment_method or "Not configured",
                "net_pay": float(net_pay),
                "reason": "Non-ACH payment method",
            })
            continue
        if net_pay <= 0:
            frappe.throw(_("Salary Slip {0} has non-positive net pay and cannot be exported.").format(slip.name))

        credentials = get_employee_ach_credentials_for_export(employee, on_date=effective_date)
        account_name = credentials.get("account_holder_name") or slip.employee_name or employee
        entries.append(ACHCredit(
            employee=employee,
            account_name=account_name,
            routing_number=credentials["routing_number"],
            account_number=credentials["account_number"],
            account_type=credentials["account_type"],
            amount=net_pay,
            individual_id=employee,
        ))

    if not entries:
        frappe.throw(_("No employees configured for ACH were found in this payroll."))

    ach_total = sum((Decimal(str(e.amount)) for e in entries), Decimal("0.00")).quantize(Decimal("0.01"))
    if ach_total > total_net_pay:
        frappe.throw(_("ACH total cannot exceed total payroll net pay."))

    return {
        "payroll_entry": pe,
        "context": ctx,
        "profile": profile,
        "effective_date": effective_date,
        "entries": entries,
        "excluded": excluded,
        "total_net_pay": total_net_pay,
        "ach_total": ach_total,
        "salary_slips": [row["name"] for row in slips],
    }


def generate_payroll_nacha_file(payroll_entry_name: str, profile_name: str, effective_date):
    plan = build_payroll_export_plan(payroll_entry_name, profile_name, effective_date)
    export_version = _next_export_version(payroll_entry_name)
    formatter_profile = _profile_to_formatter(plan["profile"], plan["effective_date"])
    export = build_payroll_ach_export(
        profile=formatter_profile,
        entries=plan["entries"],
        payroll_entry=payroll_entry_name,
        effective_date=plan["effective_date"],
        export_version=export_version,
        creation_datetime=now_datetime(),
    )

    audit = frappe.get_doc({
        "doctype": "RootedOps NACHA Export",
        "payroll_entry": payroll_entry_name,
        "company": plan["context"]["company"],
        "pay_period_start": plan["context"]["start_date"],
        "pay_period_end": plan["context"]["end_date"],
        "effective_ach_date": plan["effective_date"],
        "nacha_profile": profile_name,
        "mode": "Test" if plan["profile"].get("certification_status") == "Ready for Bank Test" else "Production",
        "export_version": export_version,
        "employee_count": export.entry_count,
        "excluded_employee_count": len(plan["excluded"]),
        "total_credits": Decimal(export.credit_total_cents) / Decimal(100),
        "entry_hash": export.entry_hash,
        "record_count": export.record_count,
        "file_name": export.filename,
        "file_sha256": export.sha256,
        "status": "Validated",
        "generated_by": frappe.session.user,
        "generated_at": now_datetime(),
    })
    audit.insert(ignore_permissions=True)
    frappe.db.commit()

    return {
        "export_name": audit.name,
        "filename": export.filename,
        "file_content": export.content,
        "sha256": export.sha256,
        "entry_count": export.entry_count,
        "entry_hash": export.entry_hash,
        "credit_total": float(Decimal(export.credit_total_cents) / Decimal(100)),
        "record_count": export.record_count,
        "excluded": plan["excluded"],
        "total_net_pay": float(plan["total_net_pay"]),
    }
