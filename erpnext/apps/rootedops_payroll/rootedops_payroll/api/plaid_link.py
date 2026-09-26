import frappe

from rootedops_payroll.services.plaid_link import create_link_token


@frappe.whitelist()
def create_profile_link_token(profile_name: str, client_name: str = "RootedOps"):
    """Create a Plaid Link token only for an explicitly selected profile."""
    if not frappe.has_permission("RootedOps Plaid Connection Profile", ptype="write"):
        frappe.throw("You do not have permission to create a Plaid Link session.", frappe.PermissionError)
    return create_link_token(profile_name, client_name=client_name)
