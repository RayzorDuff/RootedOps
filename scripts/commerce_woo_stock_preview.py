#!/usr/bin/env python3
"""READ-ONLY preview of accepted MP inventory against existing Woo draft products.

Input: operator-verified CSV from mp_commerce_inventory; WooCommerce HTTPS
GET only. Never creates products, posts stock, changes ERP/MP or toggles sync.
Refuse missing/ambiguous ownership; output a private CSV and exception summary.
"""
import argparse
import csv
import json
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "integrations/commerce"))
from ecwid_migrate import api
from staging_origin import staging_origin
from commerce_mp_reverse_link import EXPECTED

EXPECTED_FIELDS = (
    "ecommerce_id", "erp_item_code", "external_sku", "external_product_id",
    "external_variation_id", "provider", "site_key", "physical_quantity",
    "projected_quantity"
)
COLS = (
    "ecommerce_id", "erp_item_code", "ecwid_product_id", "woo_id",
    "woo_status", "woo_type", "woo_sku", "woo_source_key", "woo_manage_stock",
    "woo_current_qty", "mp_physical_qty", "mp_available_qty", "proposed_delta",
    "result"
)

def exact_meta(product, key):
    matches = [m.get("value") for m in product.get("meta_data", []) if m.get("key") == key]
    if len(matches) > 1:
        raise ValueError("Duplicate Woo metadata key for product %s" % product["id"])
    return str(matches[0]) if matches else ""

def read_source(path):
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != EXPECTED_FIELDS:
            raise ValueError("Unexpected MP inventory snapshot schema")
        rows = list(reader)
    expected = {str(mp_id): (sku, product) for mp_id, sku, product in EXPECTED}
    if len(rows) != 24 or {r["ecommerce_id"] for r in rows} != set(expected):
        raise ValueError("MP source snapshot must be exactly the 24 approved IDs")
    for r in rows:
        sku, product = expected[r["ecommerce_id"]]
        if (r["erp_item_code"] != sku or r["external_sku"] != sku
                or r["external_product_id"] != product
                or r["external_variation_id"] or r["provider"] != "ecwid"
                or r["site_key"] != "dank_mushrooms"):
            raise ValueError("MP identity drift for " + r["ecommerce_id"])
        physical = int(r["physical_quantity"])
        available = int(r["projected_quantity"])
        if not (0 <= available <= physical):
            raise ValueError("Invalid source availability for " + sku)
    return rows

def get_woo(shop, authorization, sku):
    from urllib.parse import urlencode
    endpoint = shop + "/wp-json/wc/v3/products?" + urlencode(
        {"sku": sku, "per_page": 100, "status": "any"})
    # Woo v3 products SKU filter includes draft products for authorized users.
    matches = api(endpoint, authorization)
    if not isinstance(matches, list):
        raise ValueError("Invalid Woo response type")
    return [p for p in matches if p.get("sku") == sku]

def preview(snapshot, shop, authorization):
    records = []
    seen_ids = set()
    for source in snapshot:
        sku = source["external_sku"]
        mp_id = source["ecommerce_id"]
        matches = get_woo(shop, authorization, sku)
        if len(matches) != 1:
            records.append({"ecommerce_id": mp_id, "erp_item_code": sku,
                            "ecwid_product_id": source["external_product_id"],
                            "result": "MISSING" if not matches else "AMBIGUOUS"})
            continue
        p = matches[0]
        woo_id = p.get("id")
        key = exact_meta(p, "_rootedops_source_key")
        expected_key = "ecwid:95802503:product:" + source["external_product_id"]
        marker = exact_meta(p, "_rootedops_erp_item")
        # SKU is necessary but insufficient. Require independently recorded
        # original Ecwid ownership marker; optional ERP marker must agree.
        valid = (type(woo_id) is int and woo_id > 0 and woo_id not in seen_ids
                 and key == expected_key
                 and (not marker or marker == sku)
                 and p.get("status") == "draft"
                 and p.get("type") == "simple"
                 and p.get("catalog_visibility") == "hidden")
        seen_ids.add(woo_id)
        current = p.get("stock_quantity")
        available = int(source["projected_quantity"])
        delta = available - current if type(current) is int else ""
        records.append({
            "ecommerce_id": mp_id, "erp_item_code": sku,
            "ecwid_product_id": source["external_product_id"],
            "woo_id": woo_id, "woo_status": p.get("status"),
            "woo_type": p.get("type"), "woo_sku": p.get("sku"),
            "woo_source_key": key,
            "woo_manage_stock": p.get("manage_stock"),
            "woo_current_qty": current,
            "mp_physical_qty": source["physical_quantity"],
            "mp_available_qty": available,
            "proposed_delta": delta,
            "result": "IDENTITY_OK" if valid else "REVIEW_IDENTITY"
        })
    return records

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--shop-url", default="https://shop-test.danks.store")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    shop = staging_origin(args.shop_url, "shop")
    if args.output.exists():
        parser.error("Refusing overwrite of an existing receipt")
    if not os.environ.get("WC_AUTHORIZATION"):
        parser.error("WC_AUTHORIZATION must be available privately (Basic credential header)")
    rows = read_source(args.snapshot)
    result = preview(rows, shop, os.environ["WC_AUTHORIZATION"])
    args.output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=COLS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(result)
    from collections import Counter
    print("READ ONLY: Woo draft identity/quantity projection preview")
    print("Counts:", dict(Counter(r["result"] for r in result)))
    print("Proposed quantity changes:", sum(1 for r in result if isinstance(r.get("proposed_delta"), int) and r["proposed_delta"]))
    print("Receipt:", args.output)
    print("No Woo writes were made")
    return 0 if all(r["result"] == "IDENTITY_OK" for r in result) else 2

if __name__ == "__main__":
    raise SystemExit(main())
