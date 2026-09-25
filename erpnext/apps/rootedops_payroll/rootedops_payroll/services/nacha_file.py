"""Pure NACHA PPD formatter and validator for synthetic/export-ready data."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
import re

RECORD_LENGTH = 94
BLOCKING_FACTOR = 10
SERVICE_CLASS_CREDITS_ONLY = "220"
TRANSACTION_CHECKING_CREDIT = "22"
TRANSACTION_SAVINGS_CREDIT = "32"
SEC_CODE_PPD = "PPD"
ENTRY_DESCRIPTION_PAYROLL = "PAYROLL"


def _digits(value: object) -> str:
    return re.sub(r"\D", "", str(value or ""))


def validate_routing_number(value: object) -> str:
    s = _digits(value)
    if len(s) != 9 or sum((7, 3, 9, 7, 3, 9, 7, 3, 9)[i] * int(ch) for i, ch in enumerate(s)) % 10:
        raise ValueError("Routing number must be a valid 9-digit ABA routing number")
    return s


def _amount(value: object) -> int:
    d = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if d <= 0 or d >= Decimal("100000000.00"):
        raise ValueError("ACH entry amount must be positive and fit NACHA field width")
    return int(d * 100)


def _field(value: object, length: int, *, align: str = "left", fill: str = " ") -> str:
    s = str(value or "")[:length]
    return s.ljust(length, fill) if align == "left" else s.rjust(length, fill)


def _record(parts: list[str]) -> str:
    s = "".join(parts)
    if len(s) != RECORD_LENGTH:
        raise ValueError(f"NACHA record is {len(s)} characters; expected 94")
    return s


@dataclass(frozen=True)
class ACHCredit:
    employee: str
    account_name: str
    routing_number: str
    account_number: str
    account_type: str
    amount: Decimal | str | float
    individual_id: str = ""


@dataclass(frozen=True)
class NACHAProfile:
    immediate_destination: str
    immediate_origin: str
    destination_name: str
    origin_name: str
    company_name: str
    company_id: str
    odfi_identification: str
    effective_entry_date: str
    file_id_modifier: str = "A"
    reference_code: str = ""
    balance_mode: str = "unbalanced"
    batch_number: int = 1


def build_file_header(profile: NACHAProfile, creation_date: str, creation_time: str) -> str:
    dest = _digits(profile.immediate_destination)
    orig = _digits(profile.immediate_origin)
    if len(dest) != 9 or len(orig) != 10:
        raise ValueError("Immediate Destination must be 9 digits and Immediate Origin 10 digits")
    return _record([
        "1", "01", _field(dest, 10, align="right", fill=" "),
        _field(orig, 10, align="right", fill=" "),
        _field(creation_date, 6, align="right", fill="0"),
        _field(creation_time, 4, align="right", fill="0"),
        _field(profile.file_id_modifier, 1), "094", "10", "1",
        _field(profile.destination_name.upper(), 23),
        _field(profile.origin_name.upper(), 23),
        _field(profile.reference_code, 8),
    ])


def build_batch_header(profile: NACHAProfile, company_descriptive_date: str = "") -> str:
    if profile.balance_mode != "unbalanced":
        raise ValueError("Balanced NACHA requires a configured offset account and is not implemented in Phase C")
    service = SERVICE_CLASS_CREDITS_ONLY
    company_name = profile.company_name.upper()[:16]
    company_id = _field(_digits(profile.company_id), 10, align="right", fill=" ")
    odfi = _digits(profile.odfi_identification)
    if len(odfi) != 8:
        raise ValueError("ODFI Identification must be 8 digits")
    return _record([
        "5", service, _field(company_name, 16), "".ljust(20), company_id,
        _field(SEC_CODE_PPD, 3), _field(ENTRY_DESCRIPTION_PAYROLL, 10),
        _field(company_descriptive_date, 6), _field(profile.effective_entry_date, 6),
        "   ", "1", _field(odfi, 8, align="right", fill="0"),
        _field(profile.batch_number, 7, align="right", fill="0"),
    ])


def build_entry(entry: ACHCredit, odfi: str, trace_sequence: int) -> str:
    routing = validate_routing_number(entry.routing_number)
    account_type = entry.account_type.strip().lower()
    if account_type not in {"checking", "savings"}:
        raise ValueError("Account type must be Checking or Savings")
    account = str(entry.account_number or "")
    if not account or len(account) > 17 or any(ch not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-" for ch in account):
        raise ValueError("Account number must be present and at most 17 NACHA-compatible characters")
    transaction = TRANSACTION_CHECKING_CREDIT if account_type == "checking" else TRANSACTION_SAVINGS_CREDIT
    amount = _amount(entry.amount)
    prefix = _digits(odfi)
    if len(prefix) != 8:
        raise ValueError("ODFI Identification must be 8 digits")
    trace = f"{prefix}{trace_sequence:07d}"
    return _record([
        "6", transaction, routing[:8], routing[8], _field(account, 17),
        _field(amount, 10, align="right", fill="0"),
        _field(entry.individual_id, 15),
        _field(entry.account_name.upper(), 22),
        "00", "0", _field(trace, 15),
    ])


def _control_counts(entries: list[ACHCredit], entry_hash: int, credit_total: int, debit_total: int = 0) -> str:
    return entry_hash, credit_total, debit_total


def build_batch_control(profile: NACHAProfile, entries: list[ACHCredit], entry_hash: int, credit_total: int, debit_total: int = 0) -> str:
    if profile.balance_mode != "unbalanced":
        raise ValueError("Balanced NACHA requires a configured offset account and is not implemented in Phase C")
    service = SERVICE_CLASS_CREDITS_ONLY
    odfi = _digits(profile.odfi_identification)
    return _record([
        "8", service, _field(len(entries), 6, align="right", fill="0"),
        _field(entry_hash % 10**10, 10, align="right", fill="0"),
        _field(debit_total, 12, align="right", fill="0"),
        _field(credit_total, 12, align="right", fill="0"),
        _field(_digits(profile.company_id), 10, align="right", fill=" "),
        "".ljust(19), "      ", _field(odfi, 8, align="right", fill="0"),
        _field(profile.batch_number, 7, align="right", fill="0"),
    ])


def build_file_control(batch_count: int, block_count: int, entry_count: int, entry_hash: int, debit_total: int, credit_total: int) -> str:
    return _record([
        "9", _field(batch_count, 6, align="right", fill="0"),
        _field(block_count, 6, align="right", fill="0"),
        _field(entry_count, 8, align="right", fill="0"),
        _field(entry_hash % 10**10, 10, align="right", fill="0"),
        _field(debit_total, 12, align="right", fill="0"),
        _field(credit_total, 12, align="right", fill="0"),
        "".ljust(39),
    ])


def generate_nacha(profile: NACHAProfile, entries: list[ACHCredit], *, creation_date: str, creation_time: str) -> str:
    if not entries:
        raise ValueError("At least one ACH credit is required")
    if profile.balance_mode != "unbalanced":
        raise ValueError("Balanced NACHA requires a configured offset account and is not implemented in Phase C")
    lines = [build_file_header(profile, creation_date, creation_time), build_batch_header(profile)]
    entry_records = [build_entry(e, profile.odfi_identification, i) for i, e in enumerate(entries, 1)]
    lines.extend(entry_records)
    entry_hash = sum(int(validate_routing_number(e.routing_number)[:8]) for e in entries)
    credit_total = sum(_amount(e.amount) for e in entries)
    debit_total = 0
    lines.append(build_batch_control(profile, entries, entry_hash, credit_total, debit_total))
    block_count = (len(lines) + 1 + BLOCKING_FACTOR - 1) // BLOCKING_FACTOR
    lines.append(build_file_control(1, block_count, len(entries), entry_hash, debit_total, credit_total))
    while len(lines) % BLOCKING_FACTOR:
        lines.append("9" * RECORD_LENGTH)
    text = "\n".join(lines)
    validate_nacha(text)
    return text


def validate_nacha(text: str) -> dict[str, int]:
    lines = text.splitlines()
    if not lines or len(lines) % BLOCKING_FACTOR:
        raise ValueError("NACHA file must contain complete blocks of 10 records")
    if any(len(line) != RECORD_LENGTH for line in lines):
        raise ValueError("Every NACHA record must be exactly 94 characters")
    real = [line for line in lines if line != "9" * RECORD_LENGTH]
    if not real or real[0][0] != "1" or real[-1][0] != "9":
        raise ValueError("NACHA file must begin with record 1 and end with file control record 9")
    entries = [line for line in real if line[0] == "6"]
    batch_controls = [line for line in real if line[0] == "8"]
    file_controls = [line for line in real if line[0] == "9"]
    if len(batch_controls) != 1 or len(file_controls) != 1:
        raise ValueError("Expected exactly one batch control and one file control record")
    bc, fc = batch_controls[0], file_controls[0]
    entry_hash = sum(int(e[3:11]) for e in entries) % 10**10
    credit_total = sum(int(e[29:39]) for e in entries)
    if int(bc[4:10]) != len(entries) or int(bc[10:20]) != entry_hash or int(bc[32:44]) != credit_total:
        raise ValueError("Batch control totals do not reconcile")
    if int(fc[13:21]) != len(entries) or int(fc[21:31]) != entry_hash or int(fc[43:55]) != credit_total:
        raise ValueError("File control totals do not reconcile")
    traces = [e[79:94] for e in entries]
    if len(traces) != len(set(traces)):
        raise ValueError("ACH trace numbers must be unique")
    return {"entry_count": len(entries), "entry_hash": entry_hash, "credit_total_cents": credit_total, "record_count": len(lines)}
