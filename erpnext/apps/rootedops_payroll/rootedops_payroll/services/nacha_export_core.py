"""Pure Phase E NACHA payroll-export assembly helpers."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
import hashlib
import re

from rootedops_payroll.services.nacha_file import ACHCredit, NACHAProfile, generate_nacha, validate_nacha


@dataclass(frozen=True)
class PayrollACHExport:
    content: str
    filename: str
    sha256: str
    entry_count: int
    entry_hash: int
    credit_total_cents: int
    record_count: int


def _money(value: object) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))


def _safe_filename(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "")).strip("._")
    return value or "payroll"


def default_filename(payroll_entry: str, effective_date: date, export_version: int) -> str:
    return (
        f"rootedops_payroll_{_safe_filename(payroll_entry)}_"
        f"{effective_date:%Y%m%d}_v{int(export_version)}.ach"
    )


def build_payroll_ach_export(
    *,
    profile: NACHAProfile,
    entries: list[ACHCredit],
    payroll_entry: str,
    effective_date: date,
    export_version: int,
    creation_datetime: datetime,
) -> PayrollACHExport:
    if not entries:
        raise ValueError("No ACH employees are eligible for export")
    if profile.balance_mode != "unbalanced":
        raise ValueError("Phase E export supports only a confirmed Unbalanced NACHA profile")

    content = generate_nacha(
        profile,
        entries,
        creation_date=creation_datetime.strftime("%y%m%d"),
        creation_time=creation_datetime.strftime("%H%M"),
    )
    validation = validate_nacha(content)
    credit_total = sum((_money(entry.amount) for entry in entries), Decimal("0.00"))
    if validation["credit_total_cents"] != int(credit_total * 100):
        raise ValueError("Generated NACHA credit total does not reconcile to payroll net pay")

    return PayrollACHExport(
        content=content,
        filename=default_filename(payroll_entry, effective_date, export_version),
        sha256=hashlib.sha256(content.encode("ascii")).hexdigest(),
        entry_count=validation["entry_count"],
        entry_hash=validation["entry_hash"],
        credit_total_cents=validation["credit_total_cents"],
        record_count=validation["record_count"],
    )
