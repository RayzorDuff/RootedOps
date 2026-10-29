"""Whitelisted read-only Plaid sync verification endpoint."""

import frappe

from rootedops_payroll.services.plaid_erpnext_compat import (
    enqueue_stock_compatible_synchronization as _enqueue_stock_sync,
)
from rootedops_payroll.services.plaid_sync import verify_plaid_item_sync as _verify


@frappe.whitelist()
def verify_plaid_item_sync(bank_name: str, cursor: str | None = None, count: int = 1):
    """Verify profile-aware Plaid Item sync without importing or persisting data."""
    return _verify(bank_name, cursor=cursor, count=count)



@frappe.whitelist(methods=["POST"])
def enqueue_synchronization():
    """Safely service ERPNext Plaid Settings -> Sync Now.

    Stock ERPNext queues every Bank Account with an integration ID, including
    disabled/stale rows whose parent Bank may no longer have a Plaid token.
    RootedOps limits the stock synchronizer to active accounts that are bound
    to the legacy Plaid Settings credential context.
    """
    frappe.has_permission("Plaid Settings", throw=True)
    return _enqueue_stock_sync()
