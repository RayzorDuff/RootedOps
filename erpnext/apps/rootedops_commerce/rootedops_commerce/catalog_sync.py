"""Audited native Item projections from authoritative Commercial Product Content.

Run via bench execute rootedops_commerce.catalog_sync.reconcile.
Read-only by default. No Woo, stock, pricing, tax or accounting writes.
"""
import hashlib
import json


def build_plan(rows):
    """Pure, deterministic comparison. Reject divergent native authoring."""
    changes, conflicts = [], []
    for r in sorted(rows, key=lambda row: row["item_code"]):
        code = r["item_code"]
        desired_name = r["public_title"] or ""
        desired_description = r["full_description"] or ""
        current_name = r["item_name"] or ""
        current_description = r["description"] or ""
        if not desired_name or current_name != desired_name:
            conflicts.append({"item_code": code, "field": "item_name", "reason": "title mismatch or missing authoritative title"})
        if current_description and current_description != desired_description:
            conflicts.append({"item_code": code, "field": "description", "reason": "nonempty native description differs from authoritative content"})
        if not current_description and desired_description:
            changes.append({"item_code": code, "field": "description",
                            "from": current_description, "to": desired_description})
    material = [{"item_code": r["item_code"], "item_name": r["item_name"],
                 "public_title": r["public_title"],
                 "description": r["description"], "full_description": r["full_description"],
                 "source_key": r["source_key"]}
                for r in sorted(rows, key=lambda row: row["item_code"])]
    digest = hashlib.sha256(json.dumps(material, ensure_ascii=False, sort_keys=True,
                                      separators=(",", ":")).encode("utf-8")).hexdigest()
    return {"digest": digest, "changes": changes, "conflicts": conflicts}


def reconcile(apply=False, approve_digest=None, expected_count=132):
    """Scan all linked content and only populate blank Item descriptions.

    To write: run a read-only pass, then approve its digest with the same
    exact catalog count. The candidate is recomputed against the current DB
    inside the apply transaction; any source/content drift changes the digest.
    """
    import frappe
    apply = apply in (True, 1, "1", "true", "True")
    expected_count = int(expected_count)
    if expected_count <= 0:
        raise ValueError("Positive expected_count required")
    rows = frappe.db.sql("""
        SELECT i.item_code, i.item_name, i.description,
               c.public_title, c.full_description, c.source_key
        FROM `tabItem` i
        INNER JOIN `tabCommercial Product Content` c ON c.item = i.name
        ORDER BY i.item_code
    """, as_dict=True)
    item_count = frappe.db.count("Item")
    content_count = frappe.db.count("Commercial Product Content")
    if item_count != expected_count or content_count != expected_count or len(rows) != expected_count:
        raise ValueError("Catalog count/relationship drift: expected exactly %s matching Items and content records; got Item=%s Content=%s Joined=%s" % (expected_count, item_count, content_count, len(rows)))
    plan = build_plan(rows)
    result = {"apply": apply, "item_count": item_count, "content_count": content_count,
              "matched": len(rows), "digest": plan["digest"],
              "updates_needed": len(plan["changes"]), "conflicts": plan["conflicts"],
              "sample_item_codes": [x["item_code"] for x in plan["changes"][:8]],
              "writes": False}
    if not apply:
        frappe.db.rollback()
        return result
    if not approve_digest or approve_digest != plan["digest"]:
        raise ValueError("Apply requires exact digest from immediately preceding read-only audit")
    if plan["conflicts"]:
        raise ValueError("Refusing conflicting native Item content: %s" % plan["conflicts"][:8])
    protected = ("Item", "Commercial Product Content", "Item Price",
                 "Sales Order", "Sales Invoice", "Payment Entry",
                 "Stock Entry", "Bin", "Salary Slip", "Journal Entry")
    before = {dt: frappe.db.count(dt) for dt in protected}
    try:
        for change in plan["changes"]:
            doc = frappe.get_doc("Item", change["item_code"])
            if (doc.item_name or "") != next(r["public_title"] for r in rows if r["item_code"] == change["item_code"]):
                raise ValueError("Item title changed during apply")
            if doc.description:
                raise ValueError("Item description changed during apply")
            doc.description = change["to"]
            doc.save(ignore_permissions=True)
            if frappe.db.get_value("Item", doc.name, "description") != change["to"]:
                raise ValueError("Native Item readback mismatch: %s" % doc.name)
        after = {dt: frappe.db.count(dt) for dt in protected}
        if before != after:
            raise ValueError("Protected document counts changed")
        frappe.db.commit()
    except BaseException:
        frappe.db.rollback()
        raise
    result["writes"] = bool(plan["changes"])
    result["updates_applied"] = len(plan["changes"])
    return result
