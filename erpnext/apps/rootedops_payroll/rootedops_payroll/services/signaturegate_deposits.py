"""SignatureGate cash-deposit accounting integration.

RootedOps Issue #1 establishes the ERPNext service boundary and durable
idempotency registry. SignatureGate Issue #18 supplies confirmed deposit-batch
business events. This module owns ERP account mapping, Journal Entry creation,
and native Bank Transaction reconciliation.

The initial production mapping is intentionally narrow:

* source system: SignatureGate
* source type: deposit_batch
* ERPNext company: Rooted Psyche
* income account: Donation Income - RP

Bank debit lines are derived from already-imported, unreconciled ERPNext Bank
Transactions. A deposit may therefore map to one or more bank accounts (for
example, a credit-union opening deposit split between checking and a required
share account) without teaching SignatureGate about ERPNext GL accounts.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import json
from typing import Any
from uuid import UUID

import frappe
from frappe import _
from frappe.utils import getdate, now_datetime


SOURCE_SYSTEM = "signaturegate"
SOURCE_TYPE = "deposit_batch"
COMPANY = "Rooted Psyche"
DONATION_INCOME_ACCOUNT = "Donation Income - RP"
MATCH_WINDOW_DAYS = 7
MAX_CANDIDATES_PER_DATE = 12
INTEGRATION_EVENT_DOCTYPE = "RootedOps Integration Event"


class SignatureGateDepositError(RuntimeError):
    """Raised when a confirmed cash-deposit event cannot be posted safely."""


def _to_cents(value: Any) -> int:
    try:
        amount = Decimal(str(value or "0")).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise SignatureGateDepositError(
            _("Invalid monetary amount {0}.").format(value)
        ) from exc
    return int(amount * 100)


def _money(cents: int) -> float:
    return float(Decimal(int(cents)) / Decimal(100))


def _validate_uuid(value: str) -> str:
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError, AttributeError) as exc:
        raise SignatureGateDepositError(
            _("Invalid SignatureGate deposit batch ID.")
        ) from exc


def _canonical_event(
    *,
    source_key: str,
    deposit_batch_id: str,
    status: str,
    deposit_date: str,
    deposit_slip_number: str | None,
    destination_bank_account: str | None,
    expected_amount_cents: int | None,
    actual_amount_cents: int,
    confirmed_at: str | None,
) -> dict[str, Any]:
    batch_id = _validate_uuid(deposit_batch_id)
    expected_source_key = f"{SOURCE_SYSTEM}:{SOURCE_TYPE}:{batch_id}"
    if str(source_key or "").strip() != expected_source_key:
        raise SignatureGateDepositError(
            _(
                "Source key must be {0} for this deposit batch."
            ).format(expected_source_key)
        )

    if str(status or "").strip().lower() != "confirmed":
        raise SignatureGateDepositError(
            _("SignatureGate deposit batch must be confirmed before ERP synchronization.")
        )

    actual_cents = int(actual_amount_cents or 0)
    if actual_cents <= 0:
        raise SignatureGateDepositError(
            _("Confirmed deposit amount must be positive.")
        )

    expected_cents = (
        int(expected_amount_cents)
        if expected_amount_cents not in (None, "")
        else actual_cents
    )
    if expected_cents != actual_cents:
        raise SignatureGateDepositError(
            _(
                "SignatureGate expected amount {0} cents does not equal confirmed amount {1} cents."
            ).format(expected_cents, actual_cents)
        )

    event_date = getdate(deposit_date)
    if not event_date:
        raise SignatureGateDepositError(_("Deposit date is required."))

    return {
        "source_key": expected_source_key,
        "deposit_batch_id": batch_id,
        "status": "confirmed",
        "deposit_date": str(event_date),
        "deposit_slip_number": str(deposit_slip_number or "").strip(),
        "destination_bank_account": str(destination_bank_account or "").strip(),
        "expected_amount_cents": expected_cents,
        "actual_amount_cents": actual_cents,
        "confirmed_at": str(confirmed_at or "").strip(),
    }


def _event_fingerprint(event: dict[str, Any]) -> str:
    payload = json.dumps(
        event,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _active_bank_accounts(company: str) -> dict[str, str]:
    rows = frappe.get_all(
        "Bank Account",
        filters={
            "company": company,
            "disabled": 0,
        },
        fields=["name", "account"],
        order_by="name asc",
        limit_page_length=0,
    )
    mapping = {
        str(row.get("name")): str(row.get("account"))
        for row in rows
        if row.get("name") and row.get("account")
    }
    if not mapping:
        raise SignatureGateDepositError(
            _("No active ERPNext Bank Accounts are configured for {0}.").format(company)
        )
    return mapping



def list_signaturegate_cash_deposit_bank_accounts() -> dict[str, Any]:
    """Return active Rooted Psyche ERPNext Bank Accounts for SignatureGate."""
    rows = frappe.get_all(
        "Bank Account",
        filters={
            "company": COMPANY,
            "disabled": 0,
            "is_company_account": 1,
        },
        fields=[
            "name",
            "bank",
            "account_name",
            "account",
            "mask",
            "is_default",
        ],
        order_by="is_default desc, bank asc, account_name asc, name asc",
        limit_page_length=0,
    )

    accounts = []
    for row in rows:
        name = str(row.get("name") or "").strip()
        if not name:
            continue

        account_name = str(row.get("account_name") or name).strip()
        bank = str(row.get("bank") or "").strip()
        mask = str(row.get("mask") or "").strip()

        label = account_name
        if bank:
            label += f" — {bank}"
        if mask:
            label += f" (••••{mask})"

        accounts.append(
            {
                "value": name,
                "label": label,
                "bank": bank,
                "account_name": account_name,
                "mask": mask,
                "is_default": bool(row.get("is_default")),
            }
        )

    return {
        "ok": True,
        "company": COMPANY,
        "accounts": accounts,
    }

def _candidate_bank_transactions(
    *,
    company: str,
    deposit_date: str,
) -> list[dict[str, Any]]:
    bank_accounts = _active_bank_accounts(company)
    start = getdate(deposit_date)
    end = start + timedelta(days=MATCH_WINDOW_DAYS)

    rows = frappe.get_all(
        "Bank Transaction",
        filters=[
            ["bank_account", "in", list(bank_accounts)],
            ["date", "between", [start, end]],
            ["docstatus", "=", 1],
            ["deposit", ">", 0],
            ["withdrawal", "=", 0],
            ["status", "=", "Unreconciled"],
            ["allocated_amount", "=", 0],
        ],
        fields=[
            "name",
            "bank_account",
            "date",
            "deposit",
            "withdrawal",
            "description",
            "status",
            "allocated_amount",
            "unallocated_amount",
        ],
        order_by="date asc, name asc",
        limit_page_length=0,
    )

    result = []
    for row in rows:
        item = dict(row)
        item["bank_gl_account"] = bank_accounts[item["bank_account"]]
        item["amount_cents"] = _to_cents(item.get("deposit"))
        if item["amount_cents"] > 0:
            result.append(item)
    return result


def _select_unique_match(
    candidates: list[dict[str, Any]],
    target_cents: int,
) -> tuple[str, list[dict[str, Any]]]:
    """Return one same-day subset whose deposits total the confirmed batch.

    Multiple valid subsets are intentionally treated as ambiguous rather than
    choosing by description, creation order, or fuzzy text.
    """
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in candidates:
        grouped[str(row.get("date"))].append(dict(row))

    matches: list[tuple[str, list[dict[str, Any]]]] = []

    for transaction_date, rows in sorted(grouped.items()):
        if len(rows) > MAX_CANDIDATES_PER_DATE:
            raise SignatureGateDepositError(
                _(
                    "Too many unreconciled deposit candidates on {0}; "
                    "manual review is required."
                ).format(transaction_date)
            )

        count = len(rows)
        for mask in range(1, 1 << count):
            subset = [
                rows[index]
                for index in range(count)
                if mask & (1 << index)
            ]
            total = sum(int(row["amount_cents"]) for row in subset)
            if total == int(target_cents):
                matches.append((transaction_date, subset))
                if len(matches) > 1:
                    raise SignatureGateDepositError(
                        _(
                            "More than one ERPNext Bank Transaction combination "
                            "matches the confirmed deposit amount."
                        )
                    )

    if not matches:
        raise SignatureGateDepositError(
            _(
                "No unique unreconciled ERPNext bank-deposit combination totaling "
                "{0:.2f} was found within {1} days of the SignatureGate deposit date."
            ).format(_money(target_cents), MATCH_WINDOW_DAYS)
        )

    return matches[0]


def preview_signaturegate_cash_deposit_match(
    deposit_date: str,
    actual_amount_cents: int,
    company: str = COMPANY,
) -> dict[str, Any]:
    """Read-only production preflight for the bank-transaction match."""
    target_cents = int(actual_amount_cents or 0)
    if target_cents <= 0:
        raise SignatureGateDepositError(_("Deposit amount must be positive."))

    candidates = _candidate_bank_transactions(
        company=company,
        deposit_date=deposit_date,
    )
    posting_date, matched = _select_unique_match(candidates, target_cents)

    return {
        "company": company,
        "deposit_date": str(getdate(deposit_date)),
        "posting_date": posting_date,
        "actual_amount_cents": target_cents,
        "matched_total_cents": sum(row["amount_cents"] for row in matched),
        "bank_transactions": [
            {
                "name": row["name"],
                "bank_account": row["bank_account"],
                "bank_gl_account": row["bank_gl_account"],
                "date": str(row["date"]),
                "deposit": _money(row["amount_cents"]),
                "description": row.get("description") or "",
            }
            for row in matched
        ],
        "safety": {
            "writes": 0,
            "journal_entries_created": 0,
            "bank_transactions_reconciled": 0,
        },
    }


def _income_account(company: str) -> str:
    row = frappe.db.get_value(
        "Account",
        DONATION_INCOME_ACCOUNT,
        ["name", "company", "is_group", "disabled"],
        as_dict=True,
    )
    if not row:
        raise SignatureGateDepositError(
            _("Donation income account {0} does not exist.").format(
                DONATION_INCOME_ACCOUNT
            )
        )
    if row.company != company or row.is_group or row.disabled:
        raise SignatureGateDepositError(
            _("Donation income account {0} is not usable for {1}.").format(
                DONATION_INCOME_ACCOUNT,
                company,
            )
        )
    return row.name


def _journal_entry_accounts(
    matched: list[dict[str, Any]],
    *,
    company: str,
    total_cents: int,
) -> list[dict[str, Any]]:
    bank_totals: dict[str, int] = defaultdict(int)
    for row in matched:
        bank_totals[row["bank_gl_account"]] += int(row["amount_cents"])

    lines: list[dict[str, Any]] = []
    for account, cents in sorted(bank_totals.items()):
        lines.append(
            {
                "account": account,
                "debit_in_account_currency": _money(cents),
                "credit_in_account_currency": 0,
            }
        )

    income_line: dict[str, Any] = {
        "account": _income_account(company),
        "debit_in_account_currency": 0,
        "credit_in_account_currency": _money(total_cents),
    }

    company_doc = frappe.get_cached_doc("Company", company)
    default_cost_center = company_doc.get("cost_center")
    if default_cost_center:
        income_line["cost_center"] = default_cost_center

    lines.append(income_line)
    return lines


def _create_journal_entry(
    event: dict[str, Any],
    posting_date: str,
    matched: list[dict[str, Any]],
) -> Any:
    bank_transaction_names = ", ".join(row["name"] for row in matched)
    remark = (
        f"SignatureGate cash deposit {event['deposit_batch_id']} "
        f"({event['deposit_slip_number'] or 'no reference'}); "
        f"source date {event['deposit_date']}; "
        f"matched {bank_transaction_names}"
    )

    je = frappe.get_doc(
        {
            "doctype": "Journal Entry",
            "voucher_type": "Bank Entry",
            "company": COMPANY,
            "posting_date": posting_date,
            "user_remark": remark,
            "accounts": _journal_entry_accounts(
                matched,
                company=COMPANY,
                total_cents=event["actual_amount_cents"],
            ),
        }
    )
    je.flags.ignore_permissions = True
    je.insert(ignore_permissions=True)
    je.submit()
    return je


def _reconcile_bank_transactions(
    journal_entry_name: str,
    matched: list[dict[str, Any]],
) -> None:
    """Use the native ERPNext 16.13 reconciliation path already proven in production."""
    for row in matched:
        bt = frappe.get_doc("Bank Transaction", row["name"])
        bt.add_payment_entries(
            [
                {
                    "payment_doctype": "Journal Entry",
                    "payment_name": journal_entry_name,
                }
            ]
        )
        bt.save(ignore_permissions=True)
        bt.reload()

        linked = [
            payment
            for payment in bt.payment_entries
            if payment.payment_document == "Journal Entry"
            and payment.payment_entry == journal_entry_name
        ]
        if len(linked) != 1:
            raise SignatureGateDepositError(
                _(
                    "Bank Transaction {0} did not retain exactly one Journal Entry reconciliation link."
                ).format(bt.name)
            )

        if _to_cents(linked[0].allocated_amount) != int(row["amount_cents"]):
            raise SignatureGateDepositError(
                _(
                    "Bank Transaction {0} allocated amount does not match the deposit."
                ).format(bt.name)
            )

        if bt.status != "Reconciled" or _to_cents(bt.unallocated_amount) != 0:
            raise SignatureGateDepositError(
                _(
                    "Bank Transaction {0} was not fully reconciled."
                ).format(bt.name)
            )


def _existing_event(source_key: str):
    if not frappe.db.exists(INTEGRATION_EVENT_DOCTYPE, source_key):
        return None
    return frappe.get_doc(INTEGRATION_EVENT_DOCTYPE, source_key)


def _metadata(event_doc) -> dict[str, Any]:
    raw = event_doc.get("metadata_json") or ""
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {}


def _fingerprint_change_requires_review(event_doc, fingerprint: str) -> bool:
    """Only failed events may accept a corrected payload on retry."""
    return bool(
        event_doc
        and event_doc.request_fingerprint
        and event_doc.request_fingerprint != fingerprint
        and event_doc.status != "Failed"
    )


def _replay_response(event_doc) -> dict[str, Any]:
    metadata = _metadata(event_doc)
    return {
        "ok": True,
        "idempotent_replay": True,
        "source_key": event_doc.source_key,
        "status": event_doc.status,
        "erp_doctype": event_doc.erp_doctype,
        "erp_name": event_doc.erp_name,
        "posting_date": metadata.get("posting_date"),
        "bank_transactions": metadata.get("bank_transactions") or [],
        "actual_amount_cents": metadata.get("actual_amount_cents"),
    }


def _record_failure(
    *,
    event: dict[str, Any],
    fingerprint: str,
    attempt_number: int,
    error: str,
) -> dict[str, Any]:
    existing = _existing_event(event["source_key"])
    values = {
        "source_system": SOURCE_SYSTEM,
        "source_type": SOURCE_TYPE,
        "source_id": event["deposit_batch_id"],
        "source_key": event["source_key"],
        "status": "Failed",
        "request_fingerprint": fingerprint,
        "attempt_count": attempt_number,
        "last_attempt_at": now_datetime(),
        "last_error": str(error)[:2000],
        "metadata_json": json.dumps(
            {
                "deposit_date": event["deposit_date"],
                "actual_amount_cents": event["actual_amount_cents"],
                "deposit_slip_number": event["deposit_slip_number"],
            },
            sort_keys=True,
        ),
    }

    if existing:
        for key, value in values.items():
            existing.set(key, value)
        existing.save(ignore_permissions=True)
    else:
        frappe.get_doc(
            {
                "doctype": INTEGRATION_EVENT_DOCTYPE,
                **values,
            }
        ).insert(ignore_permissions=True)

    return {
        "ok": False,
        "source_key": event["source_key"],
        "status": "Failed",
        "error": str(error),
        "attempt_count": attempt_number,
    }


def sync_signaturegate_cash_deposit_event(
    *,
    source_key: str,
    deposit_batch_id: str,
    status: str,
    deposit_date: str,
    deposit_slip_number: str | None,
    destination_bank_account: str | None,
    expected_amount_cents: int | None,
    actual_amount_cents: int,
    confirmed_at: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    event = _canonical_event(
        source_key=source_key,
        deposit_batch_id=deposit_batch_id,
        status=status,
        deposit_date=deposit_date,
        deposit_slip_number=deposit_slip_number,
        destination_bank_account=destination_bank_account,
        expected_amount_cents=expected_amount_cents,
        actual_amount_cents=actual_amount_cents,
        confirmed_at=confirmed_at,
    )
    fingerprint = _event_fingerprint(event)

    if dry_run:
        preview = preview_signaturegate_cash_deposit_match(
            event["deposit_date"],
            event["actual_amount_cents"],
            COMPANY,
        )
        return {
            "ok": True,
            "dry_run": True,
            "source_key": event["source_key"],
            **preview,
        }

    existing = _existing_event(event["source_key"])
    if existing:
        if _fingerprint_change_requires_review(existing, fingerprint):
            return {
                "ok": False,
                "source_key": event["source_key"],
                "status": existing.status,
                "error": (
                    "The existing RootedOps integration event has a different "
                    "request fingerprint; manual review is required."
                ),
            }

        if existing.status == "Succeeded":
            if (
                existing.erp_doctype
                and existing.erp_name
                and frappe.db.exists(existing.erp_doctype, existing.erp_name)
            ):
                return _replay_response(existing)
            return {
                "ok": False,
                "source_key": event["source_key"],
                "status": existing.status,
                "error": (
                    "The integration registry says this event succeeded, but "
                    "the recorded ERP document is missing."
                ),
            }

    attempt_number = int(existing.attempt_count or 0) + 1 if existing else 1

    if existing:
        existing.status = "Processing"
        existing.request_fingerprint = fingerprint
        existing.attempt_count = attempt_number
        existing.last_attempt_at = now_datetime()
        existing.last_error = None
        existing.save(ignore_permissions=True)
    else:
        frappe.get_doc(
            {
                "doctype": INTEGRATION_EVENT_DOCTYPE,
                "source_key": event["source_key"],
                "source_system": SOURCE_SYSTEM,
                "source_type": SOURCE_TYPE,
                "source_id": event["deposit_batch_id"],
                "status": "Processing",
                "request_fingerprint": fingerprint,
                "attempt_count": attempt_number,
                "last_attempt_at": now_datetime(),
            }
        ).insert(ignore_permissions=True)

    try:
        preview = preview_signaturegate_cash_deposit_match(
            event["deposit_date"],
            event["actual_amount_cents"],
            COMPANY,
        )
        matched_names = [row["name"] for row in preview["bank_transactions"]]
        matched_rows = frappe.get_all(
            "Bank Transaction",
            filters={"name": ["in", matched_names]},
            fields=[
                "name",
                "bank_account",
                "date",
                "deposit",
                "withdrawal",
                "description",
                "status",
                "allocated_amount",
                "unallocated_amount",
            ],
            order_by="date asc, name asc",
            limit_page_length=0,
        )
        bank_accounts = _active_bank_accounts(COMPANY)
        matched = []
        for row in matched_rows:
            item = dict(row)
            item["bank_gl_account"] = bank_accounts[item["bank_account"]]
            item["amount_cents"] = _to_cents(item["deposit"])
            matched.append(item)

        je = _create_journal_entry(
            event,
            preview["posting_date"],
            matched,
        )
        _reconcile_bank_transactions(je.name, matched)

        event_doc = frappe.get_doc(
            INTEGRATION_EVENT_DOCTYPE,
            event["source_key"],
        )
        event_doc.status = "Succeeded"
        event_doc.erp_doctype = "Journal Entry"
        event_doc.erp_name = je.name
        event_doc.completed_at = now_datetime()
        event_doc.last_error = None
        metadata = {
            "posting_date": str(je.posting_date),
            "deposit_date": event["deposit_date"],
            "actual_amount_cents": event["actual_amount_cents"],
            "deposit_slip_number": event["deposit_slip_number"],
            "destination_bank_account": event["destination_bank_account"],
            "bank_transactions": [
                {
                    "name": row["name"],
                    "bank_account": row["bank_account"],
                    "amount_cents": row["amount_cents"],
                }
                for row in matched
            ],
        }
        event_doc.metadata_json = json.dumps(
            metadata,
            sort_keys=True,
            default=str,
        )
        event_doc.save(ignore_permissions=True)

        return {
            "ok": True,
            "idempotent_replay": False,
            "source_key": event["source_key"],
            "status": "Succeeded",
            "erp_doctype": "Journal Entry",
            "erp_name": je.name,
            "posting_date": str(je.posting_date),
            "actual_amount_cents": event["actual_amount_cents"],
            "bank_transactions": metadata["bank_transactions"],
        }
    except Exception as exc:
        frappe.db.rollback()
        return _record_failure(
            event=event,
            fingerprint=fingerprint,
            attempt_number=attempt_number,
            error=str(exc),
        )
