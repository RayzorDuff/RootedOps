"""Centralized profile-aware Plaid API client for RootedOps.

Issue #7 Phase 3 moves Plaid credential selection from the legacy global
``Plaid Settings`` context to the Plaid Connection Profile assigned to the
local Plaid Item. Callers should resolve a client by profile or Item and never
select credential environment variables themselves.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import requests

from rootedops_payroll.services.plaid_item import get_plaid_profile_for_bank
from rootedops_payroll.services.plaid_profile import (
    PlaidProfileError,
    get_plaid_profile_status,
    resolve_plaid_profile,
)


class PlaidClientError(RuntimeError):
    """Raised when a profile-bound Plaid request cannot be completed."""


@dataclass(frozen=True)
class PlaidClient:
    """Internal server-side Plaid API client bound to exactly one profile."""

    profile: str
    environment: str
    base_url: str
    client_id: str = field(repr=False)
    secret: str = field(repr=False)

    def post(self, path: str, payload: dict[str, Any], timeout: int = 60) -> dict[str, Any]:
        if not path.startswith("/"):
            path = "/" + path
        body = {"client_id": self.client_id, "secret": self.secret, **payload}
        try:
            response = requests.post(self.base_url + path, json=body, timeout=timeout)
        except requests.RequestException as exc:
            raise PlaidClientError(
                f"Plaid profile {self.profile} request {path} failed: {exc}"
            ) from exc

        if response.status_code != 200:
            try:
                response_payload = response.json()
            except Exception:
                response_payload = {}
            raise PlaidClientError(
                f"Plaid profile {self.profile} request {path} failed: "
                f"HTTP {response.status_code}; "
                f"{response_payload.get('error_type') or 'UNKNOWN'} / "
                f"{response_payload.get('error_code') or 'UNKNOWN'}; "
                f"{response_payload.get('error_message') or 'no message'}; "
                f"request_id={response_payload.get('request_id') or 'unknown'}"
            )
        try:
            return response.json()
        except Exception as exc:
            raise PlaidClientError(
                f"Plaid profile {self.profile} request {path} returned a non-JSON response"
            ) from exc


def get_plaid_client(profile_name: str) -> PlaidClient:
    """Resolve one Plaid Connection Profile into an internal API client."""
    try:
        resolved = resolve_plaid_profile(profile_name)
    except PlaidProfileError as exc:
        raise PlaidClientError(str(exc)) from exc
    return PlaidClient(
        profile=resolved["profile"],
        environment=resolved["environment"],
        base_url=resolved["base_url"],
        client_id=resolved["client_id"],
        secret=resolved["secret"],
    )


def get_plaid_client_for_item(bank_name: str) -> PlaidClient:
    """Resolve the Plaid client from an existing local Plaid Item (ERPNext Bank)."""
    try:
        profile_name = get_plaid_profile_for_bank(bank_name)
        return get_plaid_client(profile_name)
    except PlaidClientError:
        raise
    except Exception as exc:
        raise PlaidClientError(str(exc)) from exc


def get_plaid_client_for_bank(bank_name: str) -> PlaidClient:
    """Readable alias for callers using the ERPNext Bank representation."""
    return get_plaid_client_for_item(bank_name)


def get_plaid_client_status(profile_name: str) -> dict[str, Any]:
    """Return safe profile/client readiness metadata without credentials."""
    return get_plaid_profile_status(profile_name)
