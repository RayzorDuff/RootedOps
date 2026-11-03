#!/usr/bin/env python3
"""Read-only preflight for a full Ecwid catalog migration.

Run on an immutable Ecwid API source snapshot. Never accesses destinations,
uploads images, creates ERP records, or publishes Woo products.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

APPROVED_PILOT_IDS = {
    610276905, 610274979, 610276199, 610276670,
    610274451, 610277365, 610277364, 711335071,
    711334877, 610276912, 711335797, 711335075,
    711335798, 711335795, 711335076, 753212607,
    829845573, 828374469, 828374466, 610274980,
    610274742, 711334880,
}


def assess(source):
    if str(source.get("store_id")) != "95802503":
        raise ValueError("Unexpected Ecwid store identity")
    products = source["products"]
    categories = {str(c["id"]) for c in source["categories"]}
    ids = [str(p["id"]) for p in products]
    skus = [str(p.get("sku") or "").strip() for p in products]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate Ecwid product IDs")
    if any(not s for s in skus) or len(set(s.casefold() for s in skus)) != len(skus):
        raise ValueError("Missing or duplicate SKUs")
    if any(p.get("_combinations") is None for p in products):
        raise ValueError("Missing per-product combinations evidence")
    if any(p.get("_combinations") for p in products):
        raise ValueError("Variable products require separate reviewed migration")
    present = {int(p["id"]) for p in products}
    if not APPROVED_PILOT_IDS <= present:
        raise ValueError("Previously approved 22-product cohort incomplete")
    report = {"store_id": source["store_id"], "total": len(products),
              "cohorts": {"validated": [], "other_enabled": [], "disabled": []},
              "unresolved_category_ids": [], "image_gaps": [],
              "missing_prices": [], "missing_descriptions": [],
              "publication": "draft", "catalog_visibility": "hidden",
              "stock_quantity": 0, "backorders": "no",
              "source_authority": "Ecwid", "destination_writes": False}
    unknown = set()
    for p in products:
        key = ("validated" if int(p["id"]) in APPROVED_PILOT_IDS else
               "other_enabled" if p.get("enabled") is True else "disabled")
        report["cohorts"][key].append(str(p["id"]))
        unknown.update(str(cid) for cid in p.get("categoryIds", []) if str(cid) not in categories)
        if not (p.get("originalImageUrl") or p.get("imageUrl")):
            report["image_gaps"].append(str(p["id"]))
        if p.get("price") is None:
            report["missing_prices"].append(str(p["id"]))
        if not p.get("description"):
            report["missing_descriptions"].append(str(p["id"]))
    report["unresolved_category_ids"] = sorted(unknown)
    for cohort in report["cohorts"].values():
        cohort.sort(key=int)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, help="Private output report (mode 0600)")
    args = parser.parse_args()
    data = args.source.read_bytes()
    report = assess(json.loads(data))
    report["source_file_sha256"] = hashlib.sha256(data).hexdigest()
    if args.output:
        args.output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if args.output.exists():
            raise SystemExit("Refusing to overwrite existing preflight report")
        fd = args.output.open("x")
        try:
            args.output.chmod(0o600)
            json.dump(report, fd, indent=2)
            fd.write("\n")
        finally:
            fd.close()
    print(json.dumps({
        "total": report["total"],
        "cohort_counts": {k: len(v) for k,v in report["cohorts"].items()},
        "unresolved_category_ids": report["unresolved_category_ids"],
        "missing_images": len(report["image_gaps"]),
        "missing_prices": len(report["missing_prices"]),
        "source_file_sha256": report["source_file_sha256"],
        "destination_writes": False
    }, indent=2))


if __name__ == "__main__":
    main()
