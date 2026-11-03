"""Review-gated ERP Commerce Content -> existing WooCommerce *draft* projection.

Does not create products, publish, alter SKU/identity, price, tax, images,
stock, reservations, mappings or payments. Never uses Ecwid as new authority.
"""
from copy import deepcopy
from ecwid_migrate import api, digest
from staging_origin import staging_origin

EDITABLE = ("name", "description", "short_description")
SEO = {"_rootedops_seo_title": "seo_title",
       "_rootedops_seo_description": "seo_description"}
PROTECTED = ("id", "sku", "type", "status", "catalog_visibility",
             "regular_price", "sale_price", "price", "tax_status", "tax_class",
             "manage_stock", "stock_quantity", "stock_status", "backorders",
             "images", "categories", "attributes", "variations", "virtual",
             "downloadable")


def _meta(product, key):
    matches = [m for m in product.get("meta_data", []) if m.get("key") == key]
    if len(matches) > 1:
        raise ValueError("Duplicate Woo metadata: " + key)
    return matches[0] if matches else None


def _identity(catalog, receipt, woo):
    content = catalog["content"]
    item = catalog["item"]
    code = item["item_code"]
    source = content["source_key"]
    if not source or not code or content["item"] != code:
        raise ValueError("ERP catalog authority missing or mismatched")
    if (receipt.get("erp_item") != code or receipt.get("source_key") != source
            or type(receipt.get("woo_id")) is not int or receipt["woo_id"] <= 0):
        raise ValueError("Private ERP/Woo identity receipt mismatch")
    if (woo.get("id") != receipt["woo_id"] or woo.get("sku") != code
            or woo.get("type") != "simple" or woo.get("status") != "draft"
            or woo.get("catalog_visibility") != "hidden"):
        raise ValueError("Existing Woo draft/SKU/type/visibility mismatch")
    marker = _meta(woo, "_rootedops_source_key")
    if not marker or marker.get("value") != source:
        raise ValueError("Woo source ownership marker mismatch")
    if content.get("publication_status") != "Draft":
        raise ValueError("Only canonical Draft content can be projected into staging")
    return content, code, source


def build_plan(catalog, receipt, woo):
    content, code, source = _identity(catalog, receipt, woo)
    target = {
        "name": content.get("public_title") or "",
        "description": content.get("full_description") or "",
        "short_description": content.get("short_description") or "",
        "_rootedops_seo_title": content.get("seo_title") or "",
        "_rootedops_seo_description": content.get("seo_description") or "",
    }
    if not target["name"]:
        raise ValueError("Missing canonical public title")
    current = {key: woo.get(key) or "" for key in EDITABLE}
    for key in SEO:
        record = _meta(woo, key)
        current[key] = (record or {}).get("value") or ""
    changes = {key: value for key, value in target.items() if current[key] != value}
    immutable = {key: deepcopy(woo.get(key)) for key in PROTECTED}
    fingerprint = digest({
        "schema_version": 1, "erp_item": code, "source_key": source,
        "woo_id": receipt["woo_id"], "content_modified": str(content.get("modified") or ""),
        "woo_modified": str(woo.get("date_modified_gmt") or ""),
        "before": current, "target": target, "immutable": immutable,
    })
    return {"schema_version": 1, "erp_item": code, "woo_id": receipt["woo_id"],
            "source_key": source, "digest": fingerprint,
            "changed_fields": sorted(changes), "writes": False,
            "_changes": changes, "_immutable": immutable}


def _payload(woo, changes):
    payload = {k: v for k, v in changes.items() if k in EDITABLE}
    seo = []
    for key in SEO:
        if key not in changes:
            continue
        old = _meta(woo, key)
        update = {"key": key, "value": changes[key]}
        if old and old.get("id") is not None:
            update["id"] = old["id"]
        seo.append(update)
    if seo:
        payload["meta_data"] = seo
    return payload


def sync_staging(shop_origin, authorization, catalog, receipt,
                 approve_digest=None, request=api):
    """Default read-only. Explicit matching digest allows one guarded draft edit.

    A stale digest refuses before any PUT. Post-PUT read-back either verifies
    the exact editorial projection and untouched protected fields or reports
    an error for operator reconciliation; it never retries a failed write.
    """
    shop = staging_origin(shop_origin, "shop")
    if type(receipt.get("woo_id")) is not int or receipt["woo_id"] <= 0:
        raise ValueError("Approved private Woo product ID required")
    root = shop + "/wp-json/wc/v3/products/" + str(receipt["woo_id"])
    before = request(root + "?context=edit", authorization)
    plan = build_plan(catalog, receipt, before)
    public_plan = {k: v for k, v in plan.items() if not k.startswith("_")}
    if approve_digest is None:
        return public_plan
    if approve_digest != plan["digest"]:
        raise ValueError("Approved editorial/Woo fingerprint drift; rerun preview")
    if not plan["_changes"]:
        public_plan.update(applied=True, writes=False, idempotent=True)
        return public_plan
    request(root, authorization, "PUT", _payload(before, plan["_changes"]))
    after = request(root + "?context=edit", authorization)
    # Ensure a channel write did not inadvertently change business state.
    _identity(catalog, receipt, after)
    if any(after.get(k) != v for k, v in plan["_immutable"].items()):
        raise ValueError("Protected Woo field drift after editorial PUT; reconcile manually")
    recheck = build_plan(catalog, receipt, after)
    if recheck["changed_fields"]:
        raise ValueError("Woo editorial read-back mismatch; reconcile manually")
    public_plan.update(applied=True, writes=True, idempotent=False)
    return public_plan
