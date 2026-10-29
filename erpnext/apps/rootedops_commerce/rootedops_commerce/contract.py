"""Pure identity/validation helpers; no inventory writes or framework dependency."""
import hashlib
import json


def mapping_key(provider, site_key, product_id, variation_id=None):
    parts = [str(provider or "").strip().lower(), str(site_key or "").strip(),
             str(product_id or "").strip(), str(variation_id or "").strip()]
    if not all(parts[:3]):
        raise ValueError("provider, site_key and external_product_id are required")
    return hashlib.sha256(json.dumps(parts, separators=(",", ":")).encode()).hexdigest()


def compose_projection(content, mapping, inventory):
    """Combine independently authoritative inputs; fail closed on identity mismatch."""
    if content["item"] != mapping["item"] or inventory["erp_item_code"] != content["item"]:
        raise ValueError("ERP Item identity mismatch")
    if str(inventory["ecommerce_id"]) != str(mapping["mushroomprocess_ecommerce_id"]):
        raise ValueError("MushroomProcess mapping mismatch")
    quantity = inventory["desired_quantity"]
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 0:
        raise ValueError("Inventory quantity must be a non-negative integer")
    result = dict(content)
    for override in content.get("channel_overrides", []):
        if (override["provider"], override["site_key"]) == (mapping["provider"], mapping["site_key"]):
            for key in ("title", "short_description", "full_description"):
                if override.get(key):
                    result["public_title" if key == "title" else key] = override[key]
    return {"content": result, "mapping": mapping, "quantity": quantity,
            "inventory_authority": "mushroomprocess"}
