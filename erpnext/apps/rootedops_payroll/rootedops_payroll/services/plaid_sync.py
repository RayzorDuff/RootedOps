"""Profile-aware, read-only Plaid transaction-sync verification for RootedOps.

Phase 5 deliberately does not persist a Plaid cursor or Bank Transactions. It
proves that an existing Item resolves its assigned connection profile and that
both Item status and /transactions/sync use that profile. Production import and
cursor persistence remain a separate phase.
"""

from __future__ import annotations

from hashlib import sha256
from typing import Any

import frappe
from frappe import _

from rootedops_payroll.services.plaid_client import PlaidClientError, get_plaid_client_for_bank
from rootedops_payroll.services.plaid_item import (
    PLAID_ACCESS_TOKEN_FIELD,
    _require_item_model,
    get_plaid_profile_for_bank,
)


class PlaidSyncError(RuntimeError):
    """Raised when a profile-aware read-only sync verification cannot proceed."""


def _fingerprint(value: Any) -> str | None:
    if not value:
        return None
    return sha256(str(value).encode("utf-8")).hexdigest()[:12]


def verify_plaid_item_sync(bank_name: str, *, cursor: str | None = None, count: int = 1) -> dict[str, Any]:
    """Verify Item status and transactions/sync using the Item's assigned profile.

    No ERPNext records are written and the cursor is never persisted. The
    response contains only safe metadata and counts; access tokens, cursors,
    and transaction contents are never returned.
    """
    _require_item_model()
    profile = get_plaid_profile_for_bank(bank_name)
    access_token = frappe.db.get_value("Bank", bank_name, PLAID_ACCESS_TOKEN_FIELD)
    if not access_token:
        raise PlaidSyncError(_("Plaid Item {0} has no access token.").format(bank_name))

    try:
        client = get_plaid_client_for_bank(bank_name)
        item_response = client.post("/item/get", {"access_token": access_token})
        item = item_response.get("item") or {}
        item_error = item.get("error") or {}
        if item_error:
            raise PlaidSyncError(
                _("Plaid Item {0} is unhealthy: {1} / {2}; request_id={3}").format(
                    bank_name,
                    item_error.get("error_type") or "UNKNOWN",
                    item_error.get("error_code") or "UNKNOWN",
                    item_response.get("request_id") or "unknown",
                )
            )

        count = int(count)
        if not 1 <= count <= 100:
            raise PlaidSyncError(_("count must be between 1 and 100."))

        payload: dict[str, Any] = {"access_token": access_token, "count": count}
        if cursor:
            payload["cursor"] = str(cursor)
        sync_response = client.post("/transactions/sync", payload)
    except PlaidClientError as exc:
        raise PlaidSyncError(str(exc)) from exc

    return {
        "bank": bank_name,
        "profile": profile,
        "item_id_fingerprint": _fingerprint(item.get("item_id")),
        "institution_id": item.get("institution_id"),
        "institution_name": item.get("institution_name"),
        "update_type": sync_response.get("update_type"),
        "added_count": len(sync_response.get("added") or []),
        "modified_count": len(sync_response.get("modified") or []),
        "removed_count": len(sync_response.get("removed") or []),
        "has_more": bool(sync_response.get("has_more")),
        "next_cursor_fingerprint": _fingerprint(sync_response.get("next_cursor")),
        "safety": {
            "bank_writes": 0,
            "bank_account_writes": 0,
            "bank_transaction_writes": 0,
            "cursor_persisted": False,
        },
    }
