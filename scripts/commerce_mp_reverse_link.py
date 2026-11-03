"""Guarded 24-row MushroomProcess -> ERPNext Commerce Channel Mapping backfill.

This is an operator-run Frappe console helper, NOT a scheduled sync or catalog
migration. In the Frappe/IPython console use an explicit exec namespace:
ns = {}; exec(compile(open('/tmp/commerce_mp_reverse_link.py').read(),
'/tmp/commerce_mp_reverse_link.py', 'exec'), ns)
ns['run_backfill'](frappe, apply=False)
Repeat with apply=True only after a production backup and successful preview. Source: 2026-11-03 independently verified MP/Ecwid/ERP crosswalk.
"""
from collections import Counter

EXPECTED = (
    (1, "E1SNHBC4QANF6", "711334877"),
    (5, "7G9L2K4X1V8N3", "610276670"),
    (7, "NW8KQV90K4AWG", "711335071"),
    (9, "E3ZY47P9K64TT", "711334880"),
    (11, "1KYKS1H0R71DP", "711335076"),
    (15, "M5P9B1D6Q8R2S", "610274980"),
    (16, "R6DCKT5XES9VJ", "711335072"),
    (19, "cdbd6f64-2637-488c-b9fc-0a5a47bb7322", "610274742"),
    (23, "0KTM8VBSEHN9W", "711335074"),
    (24, "78deea9b-c56b-45d3-8fb4-36596c902002", "610274451"),
    (29, "N5L2W9K4C7JQ6", "829845573"),
    (31, "7VX24W4Z0CAYJ", "711335795"),
    (32, "f60786ed-dbb9-484f-8542-0f90c2bd5b73", "610277365"),
    (34, "PVVVDXGGZD3S4", "711335797"),
    (35, "7ZWWZSR0R2D5A", "711335798"),
    (37, "8e69307a-cb75-484d-a3dd-0ff758adb094", "610276199"),
    (38, "K7M9P2R4V8XB1", "828374469"),
    (39, "WF3B148HVX8TR", "753212607"),
    (42, "T5N92Z1CQ2NTM", "711333863"),
    (43, "W4Z7C9F2H5J1K", "610274979"),
    (49, "9H2L5P7K4M1R8", "828374466"),
    (53, "ea1d0ac5-ef1b-476d-995c-1db3ec0b438d", "610277364"),
    (54, "7K9P2W4M5X1R3", "610276912"),
    (55, "P4QPQ6RQ4ARV4", "711334876"),
)
TABLE = "`tabCommerce Channel Mapping`"
COLUMNS = ("name", "item", "provider", "site_key", "external_product_id",
           "external_variation_id", "external_sku", "mushroomprocess_ecommerce_id", "sync_enabled")

def _clean(value):
    return str(value).strip() if value is not None else ""

def _validate(rows):
    if len(EXPECTED) != 24 or len({x[0] for x in EXPECTED}) != 24 or len({x[1] for x in EXPECTED}) != 24:
        raise ValueError("Approved 24-row manifest is malformed")
    expected_by_sku = {sku: (mp_id, product) for mp_id, sku, product in EXPECTED}
    candidates = {}
    linked_ids = {}
    for row in rows:
        sku = _clean(row["external_sku"])
        code = _clean(row["item"])
        prod = _clean(row["external_product_id"])
        mapped = _clean(row["mushroomprocess_ecommerce_id"])
        if mapped:
            if mapped in linked_ids:
                raise ValueError("Duplicate MP ecommerce link in ERP mappings: " + mapped)
            linked_ids[mapped] = row["name"]
        if sku not in expected_by_sku:
            continue
        mp_id, product = expected_by_sku[sku]
        if sku in candidates:
            raise ValueError("Duplicate ERP mapping for approved SKU " + sku)
        if (row["provider"] != "ecwid" or _clean(row["site_key"]) != "95802503"
                or code != sku or prod != product
                or _clean(row["external_variation_id"])
                or int(row["sync_enabled"] or 0) != 0):
            raise ValueError("ERP identity/status drift for " + sku)
        if mapped and mapped != str(mp_id):
            raise ValueError("Existing MP link conflict for " + sku)
        candidates[sku] = row
    if len(candidates) != 24:
        raise ValueError("Expected 24 ERP matches, found " + str(len(candidates)))
    for mp_id, sku, _ in EXPECTED:
        name = candidates[sku]["name"]
        owner = linked_ids.get(str(mp_id))
        if owner is not None and owner != name:
            raise ValueError("MP ID " + str(mp_id) + " already assigned to " + owner)
    return candidates

def run_backfill(frappe, apply=False):
    """Dry-run unless apply=True; abort and rollback on any conflict.

    Does not change provider/site/SKU/Ecwid IDs, stock, status, sync flags,
    prices, modified timestamps, ERP Item, Woo products or MP quantities.
    """
    if frappe.local.site != "erp.danks.store":
        raise ValueError("Refusing unexpected ERP site: " + str(frappe.local.site))
    if not isinstance(apply, bool):
        raise TypeError("apply must be explicit bool")
    try:
        sql = ("SELECT " + ", ".join("`"+c+"`" for c in COLUMNS)
               + " FROM " + TABLE + " ORDER BY name"
               + (" FOR UPDATE" if apply else ""))
        rows = frappe.db.sql(sql, as_dict=True)
        if len(rows) != 132:
            raise ValueError("Expected existing 132 Commerce Channel Mappings, found " + str(len(rows)))
        candidates = _validate(rows)
        missing = [sku for mp_id, sku, _ in EXPECTED
                   if not _clean(candidates[sku]["mushroomprocess_ecommerce_id"])]
        print(("APPLY" if apply else "PREVIEW") + ": 24/24 exact Ecwid SKU + product ID ERP mappings; "
              + str(len(missing)) + " reverse links missing")
        for mp_id, sku, product in EXPECTED:
            print("  MP=%s ERP=%s ECWID=%s %s" % (
                mp_id, sku, product,
                "already-linked" if sku not in missing else "pending"))
        if not apply:
            frappe.db.rollback()  # No write and no lingering locks.
            print("READ ONLY: no changes committed")
            return {"matched": 24, "pending": len(missing), "applied": False}
        for mp_id, sku, product in EXPECTED:
            if sku not in missing:
                continue
            name = candidates[sku]["name"]
            frappe.db.sql(
                "UPDATE " + TABLE + " SET `mushroomprocess_ecommerce_id`=%s "
                "WHERE `name`=%s AND "
                "(`mushroomprocess_ecommerce_id` IS NULL OR `mushroomprocess_ecommerce_id`='')",
                (str(mp_id), name))
        after = frappe.db.sql(
            "SELECT " + ", ".join("`"+c+"`" for c in COLUMNS)
            + " FROM " + TABLE + " ORDER BY name FOR UPDATE", as_dict=True)
        if len(after) != len(rows) or _validate(after) is None:
            raise ValueError("Post-write link validation failed")
        expected_ids = {sku: str(mp_id) for mp_id, sku, product in EXPECTED}
        for row in after:
            sku = _clean(row["external_sku"])
            if sku in expected_ids:
                if _clean(row["mushroomprocess_ecommerce_id"]) != expected_ids[sku]:
                    raise ValueError("Post-write MP link missing for " + sku)
        before_identity = {(r["name"],) + tuple(_clean(r[c]) for c in COLUMNS[1:] if c != "mushroomprocess_ecommerce_id")
                           for r in rows}
        after_identity = {(r["name"],) + tuple(_clean(r[c]) for c in COLUMNS[1:] if c != "mushroomprocess_ecommerce_id")
                          for r in after}
        if before_identity != after_identity:
            raise ValueError("Protected ERP field drift detected")
        frappe.db.commit()
        print("COMMITTED: %s previously missing ERP reverse links, 24/24 verified; sync remains disabled" % len(missing))
        return {"matched": 24, "updated": len(missing), "applied": True}
    except Exception:
        frappe.db.rollback()
        raise
