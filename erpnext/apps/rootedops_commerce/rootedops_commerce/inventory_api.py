"""MP-owned operational availability read model. Never writes ERP stock ledger.

Endpoint is disabled until explicitly enabled in site_config.json and is
restricted to authenticated integration roles with reviewed MP identities.
"""
import hashlib
import json
from datetime import datetime, timezone
import frappe


def normalize_snapshot(payload):
    p = frappe.parse_json(payload)
    if not isinstance(p, dict):
        raise ValueError("Inventory payload must be an object")
    fields = {"erp_item_code", "ecommerce_id", "desired_quantity",
              "observed_at", "provider", "site_key"}
    if set(p) != fields:
        raise ValueError("Unknown or missing inventory fields")
    if not isinstance(p["erp_item_code"], str) or not p["erp_item_code"].strip():
        raise ValueError("Missing reviewed ERP Item")
    if not str(p["ecommerce_id"]).isdigit() or int(p["ecommerce_id"]) < 1:
        raise ValueError("Invalid MP ecommerce ID")
    qty = p["desired_quantity"]
    if isinstance(qty, bool) or not isinstance(qty, int) or qty < 0:
        raise ValueError("Invalid nonnegative operational quantity")
    if not isinstance(p["observed_at"], str):
        raise ValueError("Missing UTC snapshot timestamp")
    when = datetime.fromisoformat(p["observed_at"].replace("Z", "+00:00"))
    if when.tzinfo is None or when.utcoffset().total_seconds() != 0:
        raise ValueError("Observed timestamp must be UTC")
    if when > datetime.now(timezone.utc):
        raise ValueError("Future snapshot refused")
    for key in ("provider", "site_key"):
        if not isinstance(p[key], str) or not p[key].strip() or len(p[key]) > 140:
            raise ValueError("Invalid source identity")
    value = {
        "item": p["erp_item_code"].strip(),
        "ecommerce_id": str(int(p["ecommerce_id"])),
        "quantity": qty,
        "observed": when.strftime("%Y-%m-%d %H:%M:%S.%f"),
        "provider": p["provider"].strip().lower(),
        "site_key": p["site_key"].strip(),
    }
    value["hash"] = hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return value


@frappe.whitelist(methods=["POST"])
def update_availability(payload):
    if not frappe.conf.get("mp_inventory_erp_projection_enabled"):
        frappe.throw("MP operational availability projection is disabled")
    if not ({"System Manager", "Sales Manager"} & set(frappe.get_roles())):
        frappe.throw("MP availability writer permission required", frappe.PermissionError)
    p = normalize_snapshot(payload)
    item = frappe.get_doc("Item", p["item"])
    item.check_permission("read")
    mappings = frappe.get_all("Commerce Channel Mapping",
        filters={"item": p["item"], "mushroomprocess_ecommerce_id": p["ecommerce_id"]},
        pluck="name")
    if len(mappings) != 1:
        frappe.throw("Reviewed MP ecommerce to ERP Item mapping absent or ambiguous")
    identity = "mp-ecommerce-" + p["ecommerce_id"]
    existing = frappe.db.exists("Commerce Operational Availability", identity)
    if existing:
        doc = frappe.get_doc("Commerce Operational Availability", identity)
        if doc.item != p["item"] or doc.mushroomprocess_ecommerce_id != p["ecommerce_id"]:
            frappe.throw("Inventory identity drift")
        if str(doc.source_observed_at) > p["observed"]:
            frappe.throw("Stale operational inventory snapshot refused")
        if str(doc.source_observed_at) == p["observed"]:
            if doc.source_hash == p["hash"]:
                return {"status": "duplicate", "item": p["item"], "ecommerce_id": p["ecommerce_id"],
                        "available_quantity": p["quantity"]}
            frappe.throw("Same-timestamp operational inventory snapshot conflict")
    else:
        doc = frappe.new_doc("Commerce Operational Availability")
        doc.identity = identity
        doc.item = p["item"]
        doc.mushroomprocess_ecommerce_id = p["ecommerce_id"]
    doc.available_quantity = p["quantity"]
    doc.source_observed_at = p["observed"]
    doc.source_hash = p["hash"]
    doc.source_provider = p["provider"]
    doc.source_site = p["site_key"]
    if existing:
        doc.save(ignore_permissions=True)
    else:
        doc.insert(ignore_permissions=True)
    return {"status": "updated", "item": p["item"], "ecommerce_id": p["ecommerce_id"],
            "available_quantity": p["quantity"], "source_hash": p["hash"]}
