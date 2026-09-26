"""Profile-aware Plaid credential resolution for RootedOps.

Issue #7 Phase 1 establishes the credential-context boundary without changing
existing Plaid Items or production synchronization. Raw credentials remain
outside the DocType and are resolved server-side from protected configuration
references.
"""

from __future__ import annotations

import os
import re
from typing import Any

import frappe
from frappe import _


ALLOWED_ENVIRONMENTS = ("sandbox", "development", "production")
_PROFILE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class PlaidProfileError(RuntimeError):
    pass


def _config_value(reference: str | None) -> str | None:
    """Resolve a protected configuration reference without exposing its value."""
    if not reference:
        return None
    try:
        value = frappe.conf.get(reference)
    except Exception:
        value = None
    if value is None:
        value = os.environ.get(reference)
    return value or None


def plaid_base_url(environment: str | None) -> str:
    environment = str(environment or "").strip().lower()
    if environment not in ALLOWED_ENVIRONMENTS:
        raise PlaidProfileError(
            _("Unsupported Plaid environment {0}.").format(environment or "(blank)")
        )
    return f"https://{environment}.plaid.com"


def validate_profile_name(profile_name: str | None) -> str:
    value = str(profile_name or "").strip()
    if not _PROFILE_NAME_RE.fullmatch(value):
        raise PlaidProfileError(
            _(
                "Plaid profile name must contain only lowercase letters, numbers, "
                "hyphens, and underscores, and must start with a letter or number."
            )
        )
    return value


def validate_profile_document(doc) -> None:
    """Validate safe profile configuration; disabled profiles may be incomplete."""
    validate_profile_name(doc.profile_name)
    if doc.environment not in ALLOWED_ENVIRONMENTS:
        raise PlaidProfileError(
            _("Plaid environment must be one of: {0}.").format(
                ", ".join(ALLOWED_ENVIRONMENTS)
            )
        )

    if doc.is_default:
        existing = frappe.db.exists(
            "RootedOps Plaid Connection Profile",
            {"is_default": 1, "name": ["!=", doc.name]},
        )
        if existing:
            frappe.throw(
                _("Plaid Connection Profile {0} is already the default profile.").format(
                    existing
                )
            )

    if doc.enabled:
        if not doc.client_id_secret_ref:
            frappe.throw(_("Client ID Secret Reference is required for an enabled profile."))
        if not doc.secret_secret_ref:
            frappe.throw(_("Secret Key Reference is required for an enabled profile."))
        if not _config_value(doc.client_id_secret_ref):
            frappe.throw(
                _("Plaid Client ID cannot be resolved from {0}.").format(
                    doc.client_id_secret_ref
                )
            )
        if not _config_value(doc.secret_secret_ref):
            frappe.throw(
                _("Plaid secret cannot be resolved from {0}.").format(
                    doc.secret_secret_ref
                )
            )


def resolve_plaid_profile(profile_name: str) -> dict[str, Any]:
    """Resolve profile metadata and credentials for server-side Plaid calls."""
    profile_name = validate_profile_name(profile_name)
    doc = frappe.get_doc("RootedOps Plaid Connection Profile", profile_name)
    if not doc.enabled:
        raise PlaidProfileError(_("Plaid profile {0} is disabled.").format(profile_name))
    validate_profile_document(doc)
    client_id = _config_value(doc.client_id_secret_ref)
    secret = _config_value(doc.secret_secret_ref)
    if not client_id or not secret:
        raise PlaidProfileError(
            _("Plaid profile {0} credentials could not be resolved.").format(profile_name)
        )
    return {
        "profile": doc.name,
        "display_name": doc.display_name,
        "environment": doc.environment,
        "base_url": plaid_base_url(doc.environment),
        "client_id": client_id,
        "secret": secret,
    }


def get_plaid_profile_status(profile_name: str) -> dict[str, Any]:
    """Return safe operator-facing metadata; never return credential values."""
    profile_name = validate_profile_name(profile_name)
    doc = frappe.get_doc("RootedOps Plaid Connection Profile", profile_name)
    client_configured = bool(doc.client_id_secret_ref)
    secret_configured = bool(doc.secret_secret_ref)
    client_resolvable = bool(_config_value(doc.client_id_secret_ref)) if client_configured else False
    secret_resolvable = bool(_config_value(doc.secret_secret_ref)) if secret_configured else False
    return {
        "profile": doc.name,
        "display_name": doc.display_name,
        "enabled": bool(doc.enabled),
        "is_default": bool(doc.is_default),
        "environment": doc.environment,
        "client_id_configured": client_configured,
        "secret_configured": secret_configured,
        "credentials_resolvable": client_resolvable and secret_resolvable,
        "base_url": plaid_base_url(doc.environment),
    }


def get_default_plaid_profile() -> str:
    """Return the configured default without falling back to legacy credentials."""
    profile = frappe.db.get_value(
        "RootedOps Plaid Connection Profile", {"is_default": 1}, "name"
    )
    if not profile:
        raise PlaidProfileError(_("No default RootedOps Plaid Connection Profile is configured."))
    return profile
