"""Payroll-to-NACHA pre-export planning for RootedOps Issue #6 Phase D.

Phase D is intentionally read-only: it resolves a submitted Payroll Entry to
submitted Salary Slips, separates ACH from non-ACH employees, validates ACH
destination data, reconciles ACH totals to Salary Slip net pay, and exercises
the Phase C formatter without returning or persisting a NACHA file.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Mapping

from rootedops_payroll.services.nacha_file import ACHCredit, NACHAProfile, generate_nacha, validate_nacha


class NachaPayrollValidationError(ValueError):
    """Raised when a payroll run cannot be prepared for ACH export."""


def _money(value: Any) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))


def _date_value(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except Exception as exc:
        raise NachaPayrollValidationError(f"Invalid effective ACH date: {value}") from exc


def _payment_config_effective(configuration: Mapping[str, Any], on_date: date) -> bool:
    if not bool(configuration.get("active")):
        return False
    if configuration.get("payment_method") != "ACH":
        return False
    effective = configuration.get("effective_date")
    return not effective or _date_value(effective) <= on_date


def _effective_entry_date(value: Any) -> str:
    if not value:
        raise NachaPayrollValidationError("Effective ACH Date is required for Phase D preview.")
    return _date_value(value).strftime("%y%m%d")


def _mask(value: str | None, visible: int = 4) -> str | None:
    if not value:
        return None
    return "••••" + str(value)[-visible:]


def build_nacha_payroll_plan(
    *,
    payroll_entry: str,
    company: str,
    pay_period_start: Any,
    pay_period_end: Any,
    effective_entry_date: Any,
    profile: Mapping[str, Any],
    salary_slips: list[Mapping[str, Any]],
    payment_configurations: Mapping[str, Mapping[str, Any]],
    ach_credentials: Mapping[str, Mapping[str, Any]],
    creation_datetime: datetime | None = None,
) -> dict[str, Any]:
    """Build a non-sensitive, read-only ACH export plan from resolved payroll data."""
    if not salary_slips:
        raise NachaPayrollValidationError("No submitted Salary Slips were found for this Payroll Entry.")

    if profile.get("company") != company:
        raise NachaPayrollValidationError(
            f"NACHA Profile belongs to {profile.get('company')}, not {company}."
        )
    if not profile.get("enabled"):
        raise NachaPayrollValidationError("NACHA Profile is not enabled.")
    if profile.get("balance_mode") != "Unbalanced":
        raise NachaPayrollValidationError(
            "Phase D supports only a confirmed Unbalanced NACHA profile; balanced/offset files are deferred."
        )
    if profile.get("certification_status") == "Configuration Incomplete":
        raise NachaPayrollValidationError("NACHA Profile is not ready for export planning.")

    effective_date = _date_value(effective_entry_date)
    effective_yyyymmdd = effective_date.strftime("%y%m%d")
    if len(effective_yyyymmdd) != 6:
        raise NachaPayrollValidationError("Effective ACH Date could not be normalized to YYMMDD.")

    seen_employees: set[str] = set()
    seen_slips: set[str] = set()
    ach_rows: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    total_payroll_net_pay = Decimal("0.00")
    ach_total = Decimal("0.00")

    for slip in salary_slips:
        slip_name = str(slip.get("name") or "").strip()
        employee = str(slip.get("employee") or "").strip()
        employee_name = str(slip.get("employee_name") or employee).strip()
        net_pay = _money(slip.get("net_pay"))

        if not slip_name or not employee:
            raise NachaPayrollValidationError("A Salary Slip is missing its name or Employee.")
        if slip_name in seen_slips:
            raise NachaPayrollValidationError(f"Salary Slip {slip_name} appears more than once.")
        seen_slips.add(slip_name)
        if employee in seen_employees:
            raise NachaPayrollValidationError(
                f"Employee {employee} has more than one submitted Salary Slip in this payroll period."
            )
        seen_employees.add(employee)

        if int(slip.get("docstatus") or 0) != 1:
            raise NachaPayrollValidationError(f"Salary Slip {slip_name} is not submitted.")
        if net_pay < 0:
            raise NachaPayrollValidationError(f"Salary Slip {slip_name} has negative net pay.")
        total_payroll_net_pay += net_pay

        configuration = payment_configurations.get(employee) or {}
        method = configuration.get("payment_method")
        if method != "ACH":
            excluded.append(
                {
                    "employee": employee,
                    "employee_name": employee_name,
                    "salary_slip": slip_name,
                    "net_pay": float(net_pay),
                    "payment_method": method or "Not Configured",
                    "reason": "Not configured for ACH",
                }
            )
            continue

        if not _payment_config_effective(configuration, effective_date):
            raise NachaPayrollValidationError(
                f"Employee {employee} payroll payment configuration is not active/effective on {effective_date}."
            )

        credentials = ach_credentials.get(employee) or {}
        if not credentials.get("routing_number") or not credentials.get("account_number"):
            raise NachaPayrollValidationError(
                f"Employee {employee} is configured for ACH but valid bank credentials could not be resolved."
            )
        if net_pay <= 0:
            excluded.append(
                {
                    "employee": employee,
                    "employee_name": employee_name,
                    "salary_slip": slip_name,
                    "net_pay": float(net_pay),
                    "payment_method": "ACH",
                    "reason": "Zero net pay",
                }
            )
            continue

        account_type = credentials.get("account_type")
        if account_type not in {"Checking", "Savings"}:
            raise NachaPayrollValidationError(f"Employee {employee} has an unsupported ACH account type.")

        ach_total += net_pay
        ach_rows.append(
            {
                "employee": employee,
                "employee_name": employee_name,
                "salary_slip": slip_name,
                "net_pay": float(net_pay),
                "payment_method": "ACH",
                "account_type": account_type,
                "bank_name": credentials.get("bank_name"),
                "account_holder_name": credentials.get("account_holder_name"),
                "routing_number_masked": credentials.get("routing_number_masked") or _mask(credentials.get("routing_number")),
                "account_number_masked": credentials.get("account_number_masked") or _mask(credentials.get("account_number")),
            }
        )

    if not ach_rows:
        raise NachaPayrollValidationError("No positive-net-pay employees configured for ACH in this payroll run.")

    profile_for_formatter = NACHAProfile(
        immediate_destination=str(profile.get("immediate_destination") or ""),
        immediate_origin=str(profile.get("immediate_origin") or ""),
        destination_name=str(profile.get("immediate_destination_name") or ""),
        origin_name=str(profile.get("immediate_origin_name") or ""),
        company_name=str(profile.get("company_name") or profile.get("batch_company_name") or ""),
        company_id=str(profile.get("company_id") or ""),
        odfi_identification=str(profile.get("originating_dfi_identification") or ""),
        effective_entry_date=effective_yyyymmdd,
        reference_code=str(profile.get("reference_code") or ""),
        balance_mode="unbalanced",
    )

    formatter_entries = [
        ACHCredit(
            employee=row["employee"],
            account_name=row["account_holder_name"] or row["employee_name"],
            routing_number=ach_credentials[row["employee"]]["routing_number"],
            account_number=ach_credentials[row["employee"]]["account_number"],
            account_type=row["account_type"],
            amount=Decimal(str(row["net_pay"])),
            individual_id=row["employee"],
        )
        for row in ach_rows
    ]

    created = creation_datetime or datetime.now()
    nacha_text = generate_nacha(
        profile_for_formatter,
        formatter_entries,
        creation_date=created.strftime("%y%m%d"),
        creation_time=created.strftime("%H%M"),
    )
    formatter_validation = validate_nacha(nacha_text)
    if Decimal(formatter_validation["credit_total_cents"]) / Decimal("100") != ach_total:
        raise NachaPayrollValidationError("NACHA formatter total does not reconcile to ACH Salary Slip net pay.")

    return {
        "payroll_entry": payroll_entry,
        "company": company,
        "pay_period_start": str(pay_period_start),
        "pay_period_end": str(pay_period_end),
        "effective_entry_date": effective_date.isoformat(),
        "effective_entry_date_nacha": effective_yyyymmdd,
        "profile": profile.get("profile"),
        "profile_certification_status": profile.get("certification_status"),
        "profile_balance_mode": profile.get("balance_mode"),
        "formatter_validation": formatter_validation,
        "employee_count": len(salary_slips),
        "ach_employee_count": len(ach_rows),
        "ach_total": float(ach_total),
        "total_payroll_net_pay": float(total_payroll_net_pay),
        "excluded_count": len(excluded),
        "excluded_employees": excluded,
        "employees": ach_rows,
        "validation_status": "Ready for NACHA generation",
        "read_only": True,
        "file_generated": False,
    }


def resolve_nacha_payroll_export_plan(
    payroll_entry_name: str,
    profile_name: str,
    effective_entry_date: Any,
) -> dict[str, Any]:
    """Resolve ERPNext records and return a read-only Phase D ACH export plan."""
    import frappe
    from frappe import _
    from frappe.utils import getdate, now_datetime
    from rootedops_payroll.services.employee_payments import (
        get_employee_ach_credentials_for_export,
        get_employee_payment_configuration,
    )
    from rootedops_payroll.services.nacha_profile import get_nacha_profile_configuration
    if not frappe.db.exists("Payroll Entry", payroll_entry_name):
        frappe.throw(_("Payroll Entry {0} not found.").format(payroll_entry_name))

    pe = frappe.get_doc("Payroll Entry", payroll_entry_name)
    if pe.docstatus != 1:
        frappe.throw(_("Payroll Entry {0} must be submitted/finalized before ACH export planning.").format(payroll_entry_name))
    if not pe.company or not pe.start_date or not pe.end_date:
        frappe.throw(_("Payroll Entry must have Company, Start Date, and End Date."))

    effective_date = _date_value(effective_entry_date)
    profile = get_nacha_profile_configuration(profile_name)
    if profile.get("company") != pe.company:
        frappe.throw(_("NACHA Profile {0} belongs to {1}, not {2}.").format(profile_name, profile.get("company"), pe.company))

    employees = [row.employee for row in (pe.get("employees") or []) if getattr(row, "employee", None)]
    employees = list(dict.fromkeys(employees))
    filters: dict[str, Any] = {
        "start_date": getdate(pe.start_date),
        "end_date": getdate(pe.end_date),
        "docstatus": 1,
    }
    if employees:
        filters["employee"] = ["in", employees]
    filters["company"] = pe.company

    salary_slips = frappe.get_all(
        "Salary Slip",
        filters=filters,
        fields=["name", "employee", "employee_name", "net_pay", "docstatus"],
        order_by="creation asc",
    )
    if employees:
        selected = set(employees)
        salary_slips = [row for row in salary_slips if row.employee in selected]

    payment_configurations = {
        employee: get_employee_payment_configuration(employee)
        for employee in {row.employee for row in salary_slips}
    }
    ach_credentials = {}
    for employee, configuration in payment_configurations.items():
        if configuration.get("payment_method") == "ACH":
            ach_credentials[employee] = get_employee_ach_credentials_for_export(
                employee,
                on_date=effective_date,
            )

    return build_nacha_payroll_plan(
        payroll_entry=pe.name,
        company=pe.company,
        pay_period_start=pe.start_date,
        pay_period_end=pe.end_date,
        effective_entry_date=effective_date,
        profile=profile,
        salary_slips=[row.as_dict() for row in salary_slips],
        payment_configurations=payment_configurations,
        ach_credentials=ach_credentials,
        creation_datetime=now_datetime(),
    )
