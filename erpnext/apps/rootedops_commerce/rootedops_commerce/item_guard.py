"""Prevent native Item edits from silently diverging from commercial authority.

New/unmanaged Items are unaffected. Reviewed commerce records own the public
name and description; edit them in Commercial Product Content or its Item dialog.
"""
import frappe


def enforce_canonical_item_display(doc, method=None):
    if not doc.name:
        return
    linked = frappe.db.get_value(
        "Commercial Product Content",
        {"item": doc.name},
        ["public_title", "full_description"],
        as_dict=True,
    )
    if not linked:
        return
    if (doc.item_name or "") != (linked.public_title or ""):
        frappe.throw(
            "This Item's public title is managed by Commercial Product Content. "
            "Use the Commerce Content editor on Item."
        )
    if (doc.description or "") != (linked.full_description or ""):
        frappe.throw(
            "This Item's description is managed by Commercial Product Content. "
            "Use the Commerce Content editor on Item."
        )
