"""Profile-bound Plaid Link lifecycle helpers for RootedOps.

Issue #7 Phase 4 establishes the profile boundary across new Link sessions.
A Link token is created with an explicitly selected connection profile, and
public-token exchange is performed with that same profile. Existing Bank
records are never silently re-profiled or have their access token replaced.
"""

from __future__ import annotations

from typing import Any, Iterable

import frappe
from frappe import _

from rootedops_payroll.services.plaid_client import PlaidClientError, get_plaid_client
from rootedops_payroll.services.plaid_item import (
    PLAID_ACCESS_TOKEN_FIELD,
    PLAID_PROFILE_FIELD,
    PlaidItemProfileError,
    _require_item_model,
    _require_profile,
)


class PlaidLinkError(RuntimeError):
    """Raised when a profile-bound Plaid Link operation cannot proceed."""


def _normalize_products(products: Iterable[str] | None) -> list[str]:
    values = [str(value).strip() for value in (products or ["transactions"]) if str(value).strip()]
    if not values:
        raise PlaidLinkError(_("At least one Plaid product is required."))
    return values


def create_link_token(
    profile_name: str,
    *,
    client_name: str = "RootedOps",
    products: Iterable[str] | None = None,
    country_codes: Iterable[str] | None = None,
    language: str = "en",
    redirect_uri: str | None = None,
    user_client_id: str | None = None,
) -> dict[str, Any]:
    """Create a Plaid Link token bound to an explicit connection profile."""
    profile_name = _require_profile(profile_name)
    client = get_plaid_client(profile_name)
    product_values = _normalize_products(products)
    countries = [str(value).strip().upper() for value in (country_codes or ["US"]) if str(value).strip()]
    if not countries:
        raise PlaidLinkError(_("At least one Plaid country code is required."))

    user_id = str(user_client_id or frappe.generate_hash(length=32))
    payload: dict[str, Any] = {
        "user": {"client_user_id": user_id},
        "client_name": client_name,
        "products": product_values,
        "country_codes": countries,
        "language": language,
    }
    if redirect_uri:
        payload["redirect_uri"] = redirect_uri

    try:
        response = client.post("/link/token/create", payload)
    except PlaidClientError as exc:
        raise PlaidLinkError(str(exc)) from exc

    if not response.get("link_token"):
        raise PlaidLinkError(_("Plaid did not return a Link token."))

    return {
        "profile": profile_name,
        "link_token": response["link_token"],
        "expiration": response.get("expiration"),
        "request_id": response.get("request_id"),
    }


def exchange_public_token(profile_name: str, public_token: str) -> dict[str, Any]:
    """Exchange a Link public token using the explicitly selected profile.

    The access token is returned only to this internal server-side caller so it
    can be persisted by the controlled bind operation. This function is not a
    whitelisted endpoint and never returns the token as operator metadata.
    """
    profile_name = _require_profile(profile_name)
    public_token = str(public_token or "").strip()
    if not public_token:
        raise PlaidLinkError(_("A Plaid public token is required."))

    client = get_plaid_client(profile_name)
    try:
        response = client.post(
            "/item/public_token/exchange",
            {"public_token": public_token},
        )
    except PlaidClientError as exc:
        raise PlaidLinkError(str(exc)) from exc

    access_token = response.get("access_token")
    item_id = response.get("item_id")
    if not access_token or not item_id:
        raise PlaidLinkError(_("Plaid token exchange did not return the expected Item credentials."))

    return {
        "profile": profile_name,
        "access_token": access_token,
        "item_id": item_id,
        "access_token_fingerprint": __import__("hashlib").sha256(
            access_token.encode("utf-8")
        ).hexdigest()[:12],
        "item_id_fingerprint": __import__("hashlib").sha256(
            str(item_id).encode("utf-8")
        ).hexdigest()[:12],
    }


def bind_exchanged_item(
    bank_name: str,
    profile_name: str,
    public_token: str,
) -> dict[str, Any]:
    """Bind a newly/unlinked ERPNext Bank to the profile used for Link exchange.

    This operation refuses to overwrite an existing Plaid access token or an
    existing profile. It therefore cannot silently move an established Item
    between credential contexts.
    """
    _require_item_model()
    profile_name = _require_profile(profile_name)

    doc = frappe.get_doc("Bank", bank_name)
    existing_token = doc.get(PLAID_ACCESS_TOKEN_FIELD)
    existing_profile = doc.get(PLAID_PROFILE_FIELD)
    if existing_token:
        raise PlaidLinkError(
            _("Bank {0} already has a Plaid access token; use controlled relink/migration instead.").format(
                bank_name
            )
        )
    if existing_profile:
        raise PlaidLinkError(
            _("Bank {0} already has Plaid profile {1}; refusing to replace it implicitly.").format(
                bank_name, existing_profile
            )
        )

    exchanged = exchange_public_token(profile_name, public_token)
    client = get_plaid_client(profile_name)
    try:
        item = client.post("/item/get", {"access_token": exchanged["access_token"]}).get("item") or {}
        accounts = client.post("/accounts/get", {"access_token": exchanged["access_token"]}).get("accounts") or []
    except PlaidClientError as exc:
        raise PlaidLinkError(str(exc)) from exc

    if item.get("item_id") and item.get("item_id") != exchanged["item_id"]:
        raise PlaidLinkError(_("Plaid Item identity changed during Link completion."))

    doc.set(PLAID_PROFILE_FIELD, profile_name)
    doc.set(PLAID_ACCESS_TOKEN_FIELD, exchanged["access_token"])
    doc.save(ignore_permissions=True)
    frappe.db.commit()

    return {
        "bank": bank_name,
        "profile": profile_name,
        "item_id_fingerprint": exchanged["item_id_fingerprint"],
        "account_count": len(accounts),
        "accounts": [
            {
                "account_id_fingerprint": __import__("hashlib").sha256(
                    str(account.get("account_id") or "").encode("utf-8")
                ).hexdigest()[:12],
                "name": account.get("name"),
                "official_name": account.get("official_name"),
                "mask": account.get("mask"),
                "type": account.get("type"),
                "subtype": account.get("subtype"),
            }
            for account in accounts
        ],
    }
