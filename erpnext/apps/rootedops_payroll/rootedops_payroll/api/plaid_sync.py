"""Whitelisted read-only Plaid sync verification endpoint."""

import frappe

from rootedops_payroll.services.plaid_sync import verify_plaid_item_sync as _verify


@frappe.whitelist()
def verify_plaid_item_sync(bank_name: str, cursor: str | None = None, count: int = 1):
    """Verify profile-aware Plaid Item sync without importing or persisting data."""
    return _verify(bank_name, cursor=cursor, count=count)
