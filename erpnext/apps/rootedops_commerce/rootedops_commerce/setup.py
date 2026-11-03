"""Install namespaced, display-only ERPNext Item section for commerce editing.

The Item HTML section never stores a duplicate copy of the canonical data.
"""
def ensure_item_commerce_section():
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
    create_custom_fields({
        "Item": [
            {
                "fieldname": "rootedops_commerce_section",
                "label": "Commerce Content",
                "fieldtype": "Section Break",
                "insert_after": "description",
                "collapsible": 1,
            },
            {
                "fieldname": "rootedops_commerce_preview",
                "label": "Commerce Content (ERPNext authority)",
                "fieldtype": "HTML",
                "insert_after": "rootedops_commerce_section",
                "read_only": 1,
            },
        ],
    }, update=True)
