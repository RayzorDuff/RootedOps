"""NACHA originator/profile services for RootedOps payroll ACH.

Issue #6 Phase B establishes the company/bank configuration boundary used by
later NACHA construction. ERPNext remains authoritative for Company identity
and Bank Account identity; this module stores only NACHA-specific parameters
that ERPNext does not already model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

import frappe
from frappe import _

NACHA_SEC_CODE = "PPD"
NACHA_PAYROLL_ENTRY_DESCRIPTION = "PAYROLL"
NACHA_BATCH_COMPANY_NAME_LENGTH = 16

CERTIFICATION_INCOMPLETE = "Configuration Incomplete"
CERTIFICATION_READY_FOR_TEST = "Ready for Bank Test"
CERTIFICATION_BANK_VALIDATED = "Bank Validated"
CERTIFICATION_PRODUCTION = "Production"
CERTIFICATION_STATUSES = (
    CERTIFICATION_INCOMPLETE,
    CERTIFICATION_READY_FOR_TEST,
    CERTIFICATION_BANK_VALIDATED,
    CERTIFICATION_PRODUCTION,
)

BALANCE_MODE_UNCONFIRMED = "Unconfirmed"
BALANCE_MODE_UNBALANCED = "Unbalanced"
BALANCE_MODE_BALANCED = "Balanced"
BALANCE_MODES = (
    BALANCE_MODE_UNCONFIRMED,
    BALANCE_MODE_UNBALANCED,
    BALANCE_MODE_BALANCED,
)

_REQUIRED_READY_FIELDS = (
    ("funding_bank_account", "Funding Bank Account"),
    ("bank_name", "Bank Name"),
    ("immediate_destination", "Immediate Destination"),
    ("immediate_origin", "Immediate Origin"),
    ("immediate_destination_name", "Immediate Destination Name"),
    ("immediate_origin_name", "Immediate Origin Name"),
    ("originating_dfi_identification", "Originating DFI Identification"),
)


@dataclass(frozen=True)
class NachaCompanyIdentity:
    """Derived company values used by NACHA records.

    ``ein`` is never a second configuration value. It is normalized from
    ERPNext Company.tax_id every time the profile is validated/resolved.
    """

    legal_name: str
    company_name: str
    batch_company_name: str
    ein: str
    company_id: str


def normalize_ein(tax_id: str | None) -> str:
    """Normalize ERPNext Company.tax_id to the nine EIN digits.

    Formatting punctuation is allowed in ERPNext (for example ``12-3456789``),
    but NACHA company identity requires exactly nine digits.
    """

    digits = re.sub(r"\D", "", tax_id or "")
    if len(digits) != 9:
        raise ValueError("ERPNext Company Tax ID must contain exactly 9 EIN digits.")
    return digits


def derive_nacha_company_id(tax_id: str | None) -> str:
    """High Plains Bank Company ID: ``1`` followed by the ERPNext EIN."""

    return f"1{normalize_ein(tax_id)}"


def normalize_company_name(company_name: str | None) -> str:
    """Return the bank-required uppercase company name without punctuation."""

    value = " ".join((company_name or "").split()).upper()
    value = re.sub(r"[^A-Z0-9 ]", "", value)
    value = " ".join(value.split())
    if not value:
        raise ValueError("ERPNext Company name is required for NACHA payroll.")
    return value


def derive_company_identity(company_name: str | None, tax_id: str | None) -> NachaCompanyIdentity:
    legal_name = " ".join((company_name or "").split())
    nacha_name = normalize_company_name(legal_name)
    ein = normalize_ein(tax_id)
    return NachaCompanyIdentity(
        legal_name=legal_name,
        company_name=nacha_name,
        batch_company_name=nacha_name[:NACHA_BATCH_COMPANY_NAME_LENGTH],
        ein=ein,
        company_id=f"1{ein}",
    )


def normalize_digits(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")


def validate_odfi_identification(value: str | None) -> str:
    digits = normalize_digits(value)
    if len(digits) != 8:
        raise ValueError("Originating DFI Identification must contain exactly 8 digits.")
    return digits


def validate_immediate_destination(value: str | None) -> str:
    digits = normalize_digits(value)
    if len(digits) != 9:
        raise ValueError("Immediate Destination must contain exactly 9 routing digits.")
    return digits


def normalize_profile_text(value: str | None, max_length: int | None = None) -> str:
    normalized = " ".join((value or "").split())
    if max_length is not None and len(normalized) > max_length:
        raise ValueError(f"Value cannot exceed {max_length} characters.")
    return normalized


def profile_readiness_errors(
    profile: Mapping[str, Any],
    *,
    company_name: str | None,
    company_tax_id: str | None,
) -> list[str]:
    """Return actionable errors preventing a profile from bank-test use."""

    errors: list[str] = []

    try:
        derive_company_identity(company_name, company_tax_id)
    except ValueError as exc:
        errors.append(str(exc))

    for fieldname, label in _REQUIRED_READY_FIELDS:
        if not profile.get(fieldname):
            errors.append(f"{label} is required.")

    if profile.get("balance_mode") in (None, "", BALANCE_MODE_UNCONFIRMED):
        errors.append("Balance Mode must be confirmed as Balanced or Unbalanced.")

    destination = profile.get("immediate_destination")
    if destination:
        try:
            validate_immediate_destination(str(destination))
        except ValueError as exc:
            errors.append(str(exc))

    odfi = profile.get("originating_dfi_identification")
    if odfi:
        try:
            validate_odfi_identification(str(odfi))
        except ValueError as exc:
            errors.append(str(exc))

    origin = normalize_profile_text(str(profile.get("immediate_origin") or ""))
    if origin and len(origin) > 10:
        errors.append("Immediate Origin cannot exceed 10 characters.")

    destination_name = normalize_profile_text(str(profile.get("immediate_destination_name") or ""))
    if len(destination_name) > 23:
        errors.append("Immediate Destination Name cannot exceed 23 characters.")

    origin_name = normalize_profile_text(str(profile.get("immediate_origin_name") or ""))
    if len(origin_name) > 23:
        errors.append("Immediate Origin Name cannot exceed 23 characters.")

    reference_code = str(profile.get("reference_code") or "").strip()
    if len(reference_code) > 8:
        errors.append("Reference Code cannot exceed 8 characters.")

    return errors


def _company_values(company: str) -> dict[str, Any]:
    values = frappe.db.get_value(
        "Company",
        company,
        ["company_name", "tax_id"],
        as_dict=True,
    )
    if not values:
        frappe.throw(_("Company {0} does not exist.").format(frappe.bold(company)))
    return dict(values)


def _validate_funding_bank_account(bank_account: str | None, company: str) -> None:
    if not bank_account:
        return
    values = frappe.db.get_value(
        "Bank Account",
        bank_account,
        ["company", "is_company_account"],
        as_dict=True,
    )
    if not values:
        frappe.throw(_("Funding Bank Account {0} does not exist.").format(frappe.bold(bank_account)))
    if values.get("company") and values.get("company") != company:
        frappe.throw(
            _("Funding Bank Account {0} belongs to {1}, not {2}.").format(
                frappe.bold(bank_account),
                frappe.bold(values.get("company")),
                frappe.bold(company),
            )
        )
    if values.get("is_company_account") in (0, "0", False):
        frappe.throw(_("Funding Bank Account must be a company Bank Account."))


def validate_and_project_profile(doc: Any) -> NachaCompanyIdentity:
    """Validate a RootedOps NACHA Profile and refresh derived display fields."""

    if doc.certification_status not in CERTIFICATION_STATUSES:
        frappe.throw(_("Unsupported NACHA certification status."))
    if doc.balance_mode not in BALANCE_MODES:
        frappe.throw(_("Unsupported NACHA balance mode."))

    company = _company_values(doc.company)
    try:
        identity = derive_company_identity(company.get("company_name") or doc.company, company.get("tax_id"))
    except ValueError as exc:
        frappe.throw(_(str(exc)))

    doc.nacha_company_name = identity.batch_company_name
    doc.nacha_company_id = identity.company_id
    doc.sec_code = NACHA_SEC_CODE
    doc.company_entry_description = NACHA_PAYROLL_ENTRY_DESCRIPTION

    if doc.immediate_destination:
        try:
            doc.immediate_destination = validate_immediate_destination(doc.immediate_destination)
        except ValueError as exc:
            frappe.throw(_(str(exc)))
    if doc.originating_dfi_identification:
        try:
            doc.originating_dfi_identification = validate_odfi_identification(
                doc.originating_dfi_identification
            )
        except ValueError as exc:
            frappe.throw(_(str(exc)))

    doc.immediate_origin = normalize_profile_text(doc.immediate_origin, 10)
    doc.immediate_destination_name = normalize_profile_text(doc.immediate_destination_name, 23)
    doc.immediate_origin_name = normalize_profile_text(doc.immediate_origin_name, 23)
    doc.reference_code = normalize_profile_text(doc.reference_code, 8)

    _validate_funding_bank_account(doc.funding_bank_account, doc.company)

    readiness_errors = profile_readiness_errors(
        doc.as_dict(),
        company_name=company.get("company_name") or doc.company,
        company_tax_id=company.get("tax_id"),
    )
    doc.configuration_status = "Ready" if not readiness_errors else "Incomplete"

    requires_ready_profile = bool(doc.enabled) or doc.certification_status != CERTIFICATION_INCOMPLETE
    if requires_ready_profile and readiness_errors:
        frappe.throw(
            _("NACHA profile is not ready: {0}").format("; ".join(readiness_errors))
        )

    return identity


def get_nacha_profile_configuration(profile_name: str) -> dict[str, Any]:
    """Resolve a profile plus derived ERPNext Company identity for later generators."""

    doc = frappe.get_doc("RootedOps NACHA Profile", profile_name)
    identity = validate_and_project_profile(doc)
    return {
        "profile": doc.name,
        "enabled": bool(doc.enabled),
        "certification_status": doc.certification_status,
        "configuration_status": doc.configuration_status,
        "company": doc.company,
        "company_legal_name": identity.legal_name,
        "company_name": identity.company_name,
        "batch_company_name": identity.batch_company_name,
        "company_id": identity.company_id,
        "sec_code": NACHA_SEC_CODE,
        "company_entry_description": NACHA_PAYROLL_ENTRY_DESCRIPTION,
        "funding_bank_account": doc.funding_bank_account,
        "bank_name": doc.bank_name,
        "balance_mode": doc.balance_mode,
        "immediate_destination": doc.immediate_destination,
        "immediate_origin": doc.immediate_origin,
        "immediate_destination_name": doc.immediate_destination_name,
        "immediate_origin_name": doc.immediate_origin_name,
        "originating_dfi_identification": doc.originating_dfi_identification,
        "reference_code": doc.reference_code,
        "file_name_pattern": doc.file_name_pattern,
    }
