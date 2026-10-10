"""Compatibility helpers for ERPNext's stock Plaid UI.

Issue #7 introduced explicit Plaid Connection Profiles. ERPNext's stock
"Link a new bank account" flow still writes directly to Bank and does not know
about that custom field, while stock "Sync Now" queues every Bank Account with
an integration ID even when the account is disabled or its Bank no longer has
an access token.

This module keeps those stock UI paths safe during the transition:

* a Bank linked through the stock Plaid Settings credentials is automatically
  bound to the matching legacy-backed RootedOps profile;
* stock global synchronization is limited to active Bank Accounts whose Bank
  still has an access token and is explicitly bound to that same legacy
  credential context.

Non-legacy Plaid profiles are deliberately not sent through ERPNext's stock
synchronizer because that worker resolves the global Plaid Settings credentials
rather than the Item's RootedOps profile.
"""

from __future__ import annotations

from typing import Any

import frappe

from rootedops_payroll.services.plaid_item import (
    PLAID_ACCESS_TOKEN_FIELD,
    PLAID_PROFILE_FIELD,
)
from rootedops_payroll.services.plaid_profile import (
    LEGACY_PLAID_CLIENT_ID_REF,
    LEGACY_PLAID_SECRET_REF,
)


class PlaidERPNextCompatibilityError(RuntimeError):
    """Raised when the stock ERPNext Plaid path is ambiguous or unsafe."""


def _legacy_profile_rows() -> list[Any]:
    """Return enabled profiles backed by the stock ERPNext Plaid Settings."""
    return list(
        frappe.get_all(
            "RootedOps Plaid Connection Profile",
            filters={
                "enabled": 1,
                "client_id_secret_ref": LEGACY_PLAID_CLIENT_ID_REF,
                "secret_secret_ref": LEGACY_PLAID_SECRET_REF,
            },
            fields=["name", "is_default"],
            order_by="is_default desc, name asc",
            limit_page_length=0,
        )
    )


def get_stock_plaid_profile() -> str | None:
    """Resolve the one profile that represents ERPNext's global Plaid Settings.

    A unique default wins when multiple legacy-backed profiles exist. Otherwise
    exactly one matching profile is required. Returning None keeps a stock
    Link operation usable on installations that have not yet bootstrapped
    RootedOps profiles; an ambiguous configuration is rejected rather than
    silently assigning the wrong credential context.
    """
    rows = _legacy_profile_rows()
    if not rows:
        return None

    defaults = [row for row in rows if bool(row.get("is_default"))]
    if len(defaults) == 1:
        return defaults[0].get("name")

    if len(rows) == 1:
        return rows[0].get("name")

    raise PlaidERPNextCompatibilityError(
        "Multiple enabled RootedOps Plaid profiles reference the stock "
        "ERPNext Plaid Settings credentials and none is uniquely default."
    )


def bind_stock_linked_bank_profile(doc, method: str | None = None) -> None:
    """Populate Bank.plaid_profile during ERPNext's stock Link save.

    The stock Link flow obtains its token from the global Plaid Settings
    credentials. It therefore may only be associated with the RootedOps profile
    that explicitly references those same legacy credentials.

    Existing profile assignments are never changed.
    """
    if not getattr(doc, "meta", None) or not doc.meta.has_field(PLAID_PROFILE_FIELD):
        return
    if doc.get(PLAID_PROFILE_FIELD) or not doc.get(PLAID_ACCESS_TOKEN_FIELD):
        return

    profile = get_stock_plaid_profile()
    if profile:
        doc.set(PLAID_PROFILE_FIELD, profile)


def stock_sync_plan() -> dict[str, list[dict[str, str]]]:
    """Build a safe plan for ERPNext Plaid Settings -> Sync Now.

    This function is read-only. Disabled Bank Accounts are filtered at query
    time. Tokenless, unprofiled, and non-legacy-profile Items are reported as
    skipped rather than queued into ERPNext's global-credential synchronizer.
    """
    legacy_profiles = {row.get("name") for row in _legacy_profile_rows()}
    rows = frappe.get_all(
        "Bank Account",
        filters={
            "integration_id": ["is", "set"],
            "disabled": 0,
        },
        fields=["name", "bank"],
        order_by="name asc",
        limit_page_length=0,
    )

    candidates: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []

    for row in rows:
        bank_account = row.get("name")
        bank = row.get("bank")
        if not bank:
            skipped.append(
                {
                    "bank_account": bank_account,
                    "bank": "",
                    "reason": "Bank Account has no Bank",
                }
            )
            continue

        access_token = frappe.db.get_value("Bank", bank, PLAID_ACCESS_TOKEN_FIELD)
        profile = frappe.db.get_value("Bank", bank, PLAID_PROFILE_FIELD)

        if not access_token:
            skipped.append(
                {
                    "bank_account": bank_account,
                    "bank": bank,
                    "reason": "Bank has no Plaid access token",
                }
            )
            continue

        if not profile:
            skipped.append(
                {
                    "bank_account": bank_account,
                    "bank": bank,
                    "reason": "Bank has no RootedOps Plaid profile",
                }
            )
            continue

        if profile not in legacy_profiles:
            skipped.append(
                {
                    "bank_account": bank_account,
                    "bank": bank,
                    "reason": (
                        "Bank uses a non-legacy Plaid profile; stock ERPNext "
                        "synchronization is intentionally not used"
                    ),
                }
            )
            continue

        candidates.append(
            {
                "bank_account": bank_account,
                "bank": bank,
                "profile": profile,
            }
        )

    return {
        "candidates": candidates,
        "skipped": skipped,
    }


def enqueue_stock_compatible_synchronization() -> dict[str, Any]:
    """Queue only Bank Accounts safe for ERPNext's stock Plaid worker."""
    plan = stock_sync_plan()

    for candidate in plan["candidates"]:
        frappe.enqueue(
            (
                "erpnext.erpnext_integrations.doctype.plaid_settings."
                "plaid_settings.sync_transactions"
            ),
            bank=candidate["bank"],
            bank_account=candidate["bank_account"],
        )

    return {
        "queued_count": len(plan["candidates"]),
        "queued": plan["candidates"],
        "skipped_count": len(plan["skipped"]),
        "skipped": plan["skipped"],
    }
