"""Authenticated, permission-aware catalog reads. Frappe token auth is required."""
import frappe


@frappe.whitelist(methods=["GET"])
def catalog(item, price_list=None):
    content = frappe.get_doc("Commercial Product Content", item)
    content.check_permission("read")
    erp_item = frappe.get_doc("Item", item)
    erp_item.check_permission("read")
    prices = []
    if price_list:
        prices = frappe.get_list("Item Price", filters={"item_code": item, "price_list": price_list},
            fields=["name", "price_list", "currency", "item_price_rate", "uom", "valid_from", "valid_upto"])
    return {"schema_version": 1, "content": content.as_dict(),
            "item": {"item_code": erp_item.item_code, "disabled": erp_item.disabled,
                     "stock_uom": erp_item.stock_uom, "variant_of": erp_item.variant_of},
            "prices": prices,
            "mappings": frappe.get_list("Commerce Channel Mapping", filters={"item": item},
                fields=["name", "item", "provider", "site_key", "external_product_id",
                        "external_variation_id", "external_sku", "mushroomprocess_ecommerce_id", "sync_enabled"])}


@frappe.whitelist(methods=["POST"])
def import_product(payload):
    """Import a reviewed product into staging; POST transaction is atomic.

    Item identities, UOM/group, currency/price list and variants must be explicitly
    reviewed. Existing ERP Item and Item Price values are never overwritten.
    """
    from rootedops_commerce.contract import mapping_key
    import json
    from decimal import Decimal, InvalidOperation
    if not ({"System Manager", "Sales Manager"} & set(frappe.get_roles())):
        frappe.throw("Commerce import requires Sales Manager", frappe.PermissionError)
    data = frappe.parse_json(payload)
    content_data = dict(data["content"])
    code = content_data["item"]
    source = content_data.get("source_key")
    if not source:
        frappe.throw("Source identity is required")
    erp_data = dict(data["item"])
    if erp_data.get("item_code") != code:
        frappe.throw("Item identity mismatch")
    # Importers may not use this endpoint to change stock, balances or valuation.
    allowed = {"item_code", "item_name", "item_group", "stock_uom", "has_variants", "variant_of", "attributes", "taxes"}
    if set(erp_data) - allowed:
        frappe.throw("Unsupported Item import fields")
    for tax in erp_data.get("taxes", []):
        if set(tax) != {"item_tax_template"}:
            frappe.throw("Only reviewed Item Tax Templates allowed")
        frappe.get_doc("Item Tax Template", tax["item_tax_template"]).check_permission("read")
    if not frappe.db.exists("Item", code):
        if not erp_data.get("item_group") or not erp_data.get("stock_uom"):
            frappe.throw("Reviewed item_group and stock_uom are required")
        frappe.get_doc(dict(erp_data, doctype="Item", is_stock_item=0)).insert()
    else:
        existing_item = frappe.get_doc("Item", code)
        existing_item.check_permission("read")
        for field in ("item_group", "stock_uom", "variant_of", "has_variants"):
            if field in erp_data and (existing_item.get(field) or 0) != (erp_data[field] or 0):
                frappe.throw("Existing ERP Item identity/configuration drift")
        for table, fields in (("attributes", ("attribute", "attribute_value")),
                              ("taxes", ("item_tax_template",))):
            if table in erp_data:
                expected = sorted(tuple(row.get(f) or "" for f in fields) for row in erp_data[table])
                actual = sorted(tuple(row.get(f) or "" for f in fields) for row in existing_item.get(table))
                if actual != expected:
                    frappe.throw("Existing ERP Item attribute/tax drift")
    if frappe.db.exists("Commercial Product Content", code):
        existing = frappe.get_doc("Commercial Product Content", code)
        existing.check_permission("read")
        if existing.source_key != source or existing.source_payload != content_data.get("source_payload"):
            frappe.throw("Content source drift requires explicit reconciliation")
    else:
        # Explicit field allowlist prevents importing permissions or framework flags.
        fields = {"item", "public_title", "short_description", "full_description", "seo_title",
                  "seo_description", "gallery", "source_key", "source_payload"}
        values = {k: v for k, v in content_data.items() if k in fields}
        frappe.get_doc(dict(values, doctype="Commercial Product Content", publication_status="Draft")).insert()
    m = dict(data["mapping"])
    if m.get("item") != code:
        frappe.throw("Channel mapping Item mismatch")
    key = mapping_key(m["provider"], m["site_key"], m["external_product_id"], m.get("external_variation_id"))
    if frappe.db.exists("Commerce Channel Mapping", key):
        old = frappe.get_doc("Commerce Channel Mapping", key)
        old.check_permission("read")
        if old.item != code:
            frappe.throw("External identity already belongs to another Item")
    else:
        fields = {"item", "provider", "site_key", "external_product_id", "external_variation_id",
                  "external_sku", "mushroomprocess_ecommerce_id"}
        frappe.get_doc(dict({k:v for k,v in m.items() if k in fields},
                           doctype="Commerce Channel Mapping", sync_enabled=0)).insert()
    if data.get("price") is not None:
        price = data["price"]
        try:
            rate = Decimal(str(price["item_price_rate"]))
            if not rate.is_finite() or rate < 0:
                raise ValueError
        except (InvalidOperation, ValueError, KeyError):
            frappe.throw("Invalid reviewed price")
        price_list_doc = frappe.get_doc("Price List", price["price_list"])
        price_list_doc.check_permission("read")
        if not price_list_doc.selling or not price_list_doc.enabled or price_list_doc.currency != price["currency"]:
            frappe.throw("Reviewed selling price list/currency mismatch")
        filters = {"item_code":code, "price_list":price["price_list"],
                   "currency":price["currency"], "uom":erp_data["stock_uom"]}
        matches = frappe.get_list("Item Price", filters=filters,
                                  fields=["name", "item_price_rate", "valid_from", "valid_upto"])
        if len(matches) > 1 or (matches and Decimal(str(matches[0].item_price_rate)) != rate):
            frappe.throw("Price ambiguity/drift requires explicit reconciliation")
        if not matches:
            frappe.get_doc(dict(filters, doctype="Item Price", item_price_rate=str(rate))).insert()
    return {"item":code, "content":code, "mapping":key, "status":"imported_or_existing"}


@frappe.whitelist(methods=["POST"])
def import_reviewed_catalog(payload):
    """Atomic reviewed batch; attributes, UOM, groups, templates/lists must exist."""
    if not frappe.conf.get("commerce_catalog_import_enabled"):
        frappe.throw("Catalog batch import requires explicit site configuration")
    data = frappe.parse_json(payload)
    if not data.get("source_sha256") or not data.get("review_sha256"):
        frappe.throw("Bound source and review hashes required")
    result = []
    for record in data["records"]:
        # import_product enforces roles, permissions, allowed fields and drift.
        result.append(import_product({k: record[k] for k in ("item", "content", "mapping", "price")}))
    return {"records": result, "stock_changed": False, "financial_documents_created": False}
