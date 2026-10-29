import frappe

from rootedops_payroll.services.plaid_link import create_link_token, bind_exchanged_item


@frappe.whitelist()
def create_profile_link_token(profile_name: str, client_name: str = "RootedOps"):
    """Create a Plaid Link token only for an explicitly selected profile."""
    if not frappe.has_permission("RootedOps Plaid Connection Profile", ptype="write"):
        frappe.throw("You do not have permission to create a Plaid Link session.", frappe.PermissionError)
    return create_link_token(profile_name, client_name=client_name)


@frappe.whitelist(methods=["POST"])
def bind_profile_item(bank_name: str, profile_name: str, public_token: str):
    """Bind a separately authenticated Plaid Item to an empty Bank record.

    Never overwrite an existing Plaid Item or manipulate any Bank Account mapping.
    The browser passes the short-lived public token only; access tokens stay server-side.
    """
    if not frappe.has_permission("RootedOps Plaid Connection Profile", ptype="write"):
        frappe.throw("Permission denied for Plaid connection profiles.", frappe.PermissionError)
    frappe.get_doc("Bank", bank_name).check_permission("write")
    return bind_exchanged_item(bank_name, profile_name, public_token)
