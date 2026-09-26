"""Plaid Item/profile binding and controlled legacy migration for RootedOps.

Phase 2 establishes the relationship between ERPNext's existing Plaid Item
representation (the Bank record carrying a Plaid access token) and a RootedOps
Plaid Connection Profile. It deliberately does not call Plaid or change the
existing synchronization implementation.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

PLAID_ITEM_DOCTYPE = "Bank"
PLAID_PROFILE_FIELD = "plaid_profile"
PLAID_ACCESS_TOKEN_FIELD = "plaid_access_token"


class PlaidItemProfileError(RuntimeError):
    pass


def ensure_plaid_item_custom_fields() -> None:
    """Create the Bank → Plaid Connection Profile relationship field."""
    create_custom_fields(
        {
            PLAID_ITEM_DOCTYPE: [
                {
                    "fieldname": PLAID_PROFILE_FIELD,
                    "label": "Plaid Connection Profile",
                    "fieldtype": "Link",
                    "options": "RootedOps Plaid Connection Profile",
                    "insert_after": PLAID_ACCESS_TOKEN_FIELD,
                    "description": (
                        "Credential context for this Plaid Item. Do not change "
                        "an existing Item's profile without a controlled relink/migration."
                    ),
                    "read_only": 1,
                }
            ]
        },
        update=True,
    )


def _require_profile(profile_name: str) -> str:
    from rootedops_payroll.services.plaid_profile import validate_profile_name

    profile_name = validate_profile_name(profile_name)
    if not frappe.db.exists("RootedOps Plaid Connection Profile", profile_name):
        raise PlaidItemProfileError(
            _("Plaid Connection Profile {0} does not exist.").format(profile_name)
        )
    return profile_name


def _require_item_model() -> None:
    meta = frappe.get_meta(PLAID_ITEM_DOCTYPE)
    if not meta.has_field(PLAID_ACCESS_TOKEN_FIELD):
        raise PlaidItemProfileError(
            _("ERPNext Bank does not expose the expected Plaid access-token field.")
        )
    if not meta.has_field(PLAID_PROFILE_FIELD):
        raise PlaidItemProfileError(
            _("Plaid Connection Profile field is not installed on Bank.")
        )


def get_plaid_item_profile(bank_name: str) -> str | None:
    """Return an Item's assigned profile without falling back to the default."""
    _require_item_model()
    value = frappe.db.get_value(PLAID_ITEM_DOCTYPE, bank_name, PLAID_PROFILE_FIELD)
    return value or None


def get_plaid_profile_for_bank(bank_name: str) -> str:
    """Resolve a Bank's explicit Plaid profile; never silently use the default."""
    profile = get_plaid_item_profile(bank_name)
    if not profile:
        raise PlaidItemProfileError(
            _("Plaid Item {0} has no assigned connection profile.").format(bank_name)
        )
    return profile


def list_plaid_items() -> list[str]:
    """Return local Bank records that represent connected Plaid Items."""
    _require_item_model()
    rows = frappe.get_all(
        PLAID_ITEM_DOCTYPE,
        filters={PLAID_ACCESS_TOKEN_FIELD: ["is", "set"]},
        pluck="name",
        order_by="name asc",
    )
    return list(rows)


def _stable_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _stable_value(value[k]) for k in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_stable_value(item) for item in value]
    if value is None:
        return None
    return str(value)


def _item_state_fingerprint(bank_name: str) -> str:
    """Hash the complete pre-migration Item state except migration metadata."""
    doc = frappe.get_doc(PLAID_ITEM_DOCTYPE, bank_name)
    excluded = {
        "modified",
        "modified_by",
        "docstatus",
        PLAID_PROFILE_FIELD,
    }
    state = {
        field.fieldname: _stable_value(doc.get(field.fieldname))
        for field in doc.meta.fields
        if field.fieldname not in excluded
    }
    payload = json.dumps(state, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def snapshot_plaid_item_state() -> dict[str, Any]:
    """Capture safe fingerprints/counts before or after migration.

    No access token, cursor, or other field value is returned. The complete
    Item state is represented by a SHA-256 fingerprint so accidental changes
    can be detected without exposing sensitive values.
    """
    _require_item_model()
    items = list_plaid_items()
    bank_account_counts = {}
    transaction_counts = {}

    for bank_name in items:
        account_rows = frappe.get_all(
            "Bank Account",
            filters={"bank": bank_name},
            pluck="name",
            order_by="name asc",
        )
        bank_account_counts[bank_name] = len(account_rows)
        transaction_counts[bank_name] = {
            account_name: frappe.db.count(
                "Bank Transaction", {"bank_account": account_name, "docstatus": ["!=", 2]}
            )
            for account_name in account_rows
        }

    return {
        "item_count": len(items),
        "items": {
            name: {
                "profile": get_plaid_item_profile(name),
                "state_fingerprint": _item_state_fingerprint(name),
            }
            for name in items
        },
        "bank_account_counts": bank_account_counts,
        "bank_transaction_counts": transaction_counts,
    }


def verify_plaid_item_migration(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Compare migration snapshots and return a safe verification report."""
    before_items = before.get("items", {})
    after_items = after.get("items", {})
    before_names = set(before_items)
    after_names = set(after_items)

    errors: list[str] = []
    if before.get("item_count") != after.get("item_count"):
        errors.append("Plaid Item count changed")
    if before_names != after_names:
        errors.append("Plaid Item set changed")

    for name in sorted(before_names & after_names):
        if before_items[name]["state_fingerprint"] != after_items[name]["state_fingerprint"]:
            errors.append(f"Plaid Item state changed: {name}")
        if after_items[name]["profile"] is None:
            errors.append(f"Plaid Item has no profile: {name}")

    if before.get("bank_account_counts") != after.get("bank_account_counts"):
        errors.append("Bank Account mappings changed")
    if before.get("bank_transaction_counts") != after.get("bank_transaction_counts"):
        errors.append("Bank Transaction counts changed")

    return {
        "ok": not errors,
        "item_count": after.get("item_count", 0),
        "profiled_item_count": sum(
            1 for item in after_items.values() if item.get("profile")
        ),
        "errors": errors,
    }


def migrate_existing_plaid_items(profile_name: str, *, verify: bool = True) -> dict[str, Any]:
    """Assign an explicit profile to every legacy Plaid Item lacking one.

    This function is intentionally local-only: it never contacts Plaid,
    recreates an Item, changes an access token, or changes synchronization
    state. It is intended to be invoked explicitly after the operator has
    created and verified the migration/default profile.
    """
    _require_item_model()
    profile_name = _require_profile(profile_name)

    before = snapshot_plaid_item_state()
    assigned: list[str] = []
    already_assigned: list[str] = []

    for bank_name in list_plaid_items():
        existing = get_plaid_item_profile(bank_name)
        if existing:
            already_assigned.append(bank_name)
            continue
        frappe.db.set_value(PLAID_ITEM_DOCTYPE, bank_name, PLAID_PROFILE_FIELD, profile_name)
        assigned.append(bank_name)

    after = snapshot_plaid_item_state()
    verification = verify_plaid_item_migration(before, after)

    if verify and not verification["ok"]:
        frappe.db.rollback()
        raise PlaidItemProfileError(
            _("Plaid Item migration verification failed: {0}").format(
                "; ".join(verification["errors"])
            )
        )

    frappe.db.commit()

    return {
        "profile": profile_name,
        "assigned": assigned,
        "already_assigned": already_assigned,
        "before": {
            "item_count": before["item_count"],
            "profiled_item_count": sum(1 for item in before["items"].values() if item["profile"]),
        },
        "after": verification,
    }
