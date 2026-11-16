"""Replace generated hashes in Woo Contact display names without changing IDs."""
import frappe

from rootedops_commerce.customer_sync import LINK, apply_contact_name


def execute():
    links = frappe.get_all(LINK, filters={"customer": ["is", "set"], "contact": ["is", "set"]}, pluck="name")
    for name in links:
        link = frappe.get_doc(LINK, name, for_update=True)
        if frappe.db.get_value("Contact", link.contact, "first_name") != link.source_key:
            continue
        contact = frappe.get_doc("Contact", link.contact, for_update=True)
        if contact.first_name != link.source_key:
            continue
        if {(row.link_doctype, row.link_name) for row in contact.links} != {("Customer", link.customer)}:
            continue
        apply_contact_name(link, contact, {"first_name": "", "last_name": contact.last_name or ""})
        contact.save()
        link.save()
