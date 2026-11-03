"""Permission-checked editorial access from the native ERPNext Item form.

Commercial Product Content stays authoritative. This endpoint does not publish
WooCommerce, change stock, prices, tax or source identity.
"""
import frappe

EDITORIAL_FIELDS = (
    "public_title", "short_description", "full_description",
    "seo_title", "seo_description",
)


@frappe.whitelist(methods=["GET"])
def get_item_editorial(item):
    erp = frappe.get_doc("Item", item)
    erp.check_permission("read")
    doc = frappe.get_doc("Commercial Product Content", item)
    doc.check_permission("read")
    fields = {name: doc.get(name) or "" for name in EDITORIAL_FIELDS}
    gallery = [
        {"image": row.image, "alt_text": row.alt_text, "source_url": row.source_url}
        for row in doc.get("gallery", [])
    ]
    overrides = [
        {"provider": row.provider, "site_key": row.site_key,
         "title": row.title, "short_description": row.short_description,\n         "full_description": row.full_description}
        for row in doc.get("channel_overrides", [])
    ]
    return {
        "item": doc.item,
        "source_key": doc.source_key,
        "modified": str(doc.modified),
        "publication_status": doc.publication_status,
        "fields": fields,
        "gallery": gallery,
        "channel_overrides": overrides,
        "can_write": bool(
            doc.has_permission("write") and erp.has_permission("write")
        ),
    }


@frappe.whitelist(methods=["POST"])
def save_item_editorial(item, expected_modified, values):
    erp = frappe.get_doc("Item", item)
    erp.check_permission("write")
    doc = frappe.get_doc("Commercial Product Content", item)
    doc.check_permission("write")
    if doc.item != erp.name:
        frappe.throw("Item/content identity mismatch")
    if str(doc.modified) != str(expected_modified):
        frappe.throw("Editorial record changed since it was opened. Reload before editing.")
    values = frappe.parse_json(values)
    if not isinstance(values, dict) or set(values) != set(EDITORIAL_FIELDS):
        frappe.throw("Only reviewed editorial fields are editable here")
    if not all(isinstance(v, str) for v in values.values()):
        frappe.throw("Editorial fields must contain strings")
    if not values["public_title"].strip():
        frappe.throw("Public title is required")
    # Fail closed if the native Item was edited independently. The DocType's
    # on_update hook performs the same check for direct Commerce form edits.
    if (erp.item_name or "") != (doc.public_title or ""):
        frappe.throw("Item name differs from authoritative title")
    if (erp.description or "") != (doc.full_description or ""):
        frappe.throw("Item description differs from authoritative content")
    for name in EDITORIAL_FIELDS:
        doc.set(name, values[name])
    doc.save()
    return {"item": doc.item, "modified": str(doc.modified),
            "publication_status": doc.publication_status,
            "woo_synchronized": False}
