#!/usr/bin/env python3
"""Prepare and approve a complete, human-reviewed tax classification of Ecwid Items.

Source product titles and categories are context for review, NEVER authority
for automatic grocery classification. No ERP, WooCommerce or provider writes.
Output is private and content-addressed; an approved mapping requires every
original SKU explicitly classified, with owner-supplied rationale.
"""
import argparse
import csv
import hashlib
import json
import os
import re
from pathlib import Path

EXPECTED_SOURCE_SHA = "0b4eec40a1cfd1d62551e2ac951a42dac21984f34ffb2d03f9aea697d1d713a8"
STORE_ID = "95802503"
CLASSES = {"grocery_food", "cultivation_supply", "other_reviewed"}
POS_LABEL = re.compile(r"^(?:50c|[0-9]+ Dollar) Mushroom Item(?: \(NOTAX\))?$", re.IGNORECASE)


def load_source(path):
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != EXPECTED_SOURCE_SHA:
        raise ValueError("Immutable Ecwid source hash changed")
    source = json.loads(raw)
    if str(source.get("store_id")) != STORE_ID or len(source.get("products", [])) != 132:
        raise ValueError("Unexpected source catalog")
    products = source["products"]
    if any(p.get("_combinations") for p in products):
        raise ValueError("Variable product classification requires separate review")
    ids = [str(p["id"]) for p in products]
    skus = [str(p.get("sku") or "").strip() for p in products]
    if len(set(ids)) != 132 or len(set(s.casefold() for s in skus)) != 132 or not all(skus):
        raise ValueError("Duplicate or missing catalog identity")
    return {p["sku"].strip(): p for p in products}


def _private_write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.exists():
        raise ValueError("Refusing to overwrite existing classification artifact")
    if path.parent.stat().st_mode & 0o077:
        raise ValueError("Classification directory must be private (0700)")
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as out:
        if isinstance(value, str):
            out.write(value)
        else:
            json.dump(value, out, indent=2, ensure_ascii=False)
            out.write("\n")


def prepare(products, output):
    rows = []
    for sku, p in sorted(products.items(), key=lambda x: (x[1]["name"].casefold(), x[0])):
        rows.append({
            "item_code": sku, "ecwid_product_id": str(p["id"]),
            "name": p.get("name") or "", "source_enabled": "yes" if p.get("enabled") else "no",
            "source_category_ids": ",".join(str(x) for x in p.get("categoryIds") or []),
            "tax_class": "", "review_note": ""
        })
    import io
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    _private_write(output, buf.getvalue())
    return {"products": len(rows), "review_file": str(output),
            "complete": False, "writes_to_destinations": False}


def approve(products, review_file, output, reviewer):
    reviewer = reviewer.strip()
    if len(reviewer) < 2 or len(reviewer) > 128:
        raise ValueError("Reviewer identity required")
    with review_file.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        required = {"item_code", "ecwid_product_id", "tax_class", "review_note"}
        if not reader.fieldnames or not required <= set(reader.fieldnames):
            raise ValueError("Required CSV review columns absent")
        rows = list(reader)
    if len(rows) != 132:
        raise ValueError("Every imported product must be reviewed exactly once")
    seen = set()
    classifications = {}
    excluded = {}
    for row in rows:
        sku = row["item_code"].strip()
        if sku in seen or sku not in products:
            raise ValueError("Duplicate or foreign Item: " + sku)
        seen.add(sku)
        if row["ecwid_product_id"].strip() != str(products[sku]["id"]):
            raise ValueError("Source ID mismatch: " + sku)
        kind = row["tax_class"].strip()
        if kind not in CLASSES and (kind or
                row.get("review_status", "").strip() != "excluded_pos"):
            raise ValueError("Unreviewed or invalid tax class for: " + sku)
        note = row["review_note"].strip()
        if not note or len(note) > 1024:
            raise ValueError("Document a product-specific rationale for: " + sku)
        if kind not in CLASSES:
            # The only permitted unclassified items are explicit generic
            # dollar-amount POS buttons that do not identify a product.
            # Exclusion is NOT a tax exemption or a future sale permission.
            if (kind or row.get("review_status", "").strip() != "excluded_pos" or
                    not POS_LABEL.fullmatch(str(products[sku].get("name") or ""))):
                raise ValueError("Unreviewed or invalid tax class for: " + sku)
            excluded[sku] = {"reason": note, "source_product_id": str(products[sku]["id"])}
            continue
        if row.get("review_status", "").strip() == "excluded_pos":
            raise ValueError("Excluded POS status conflicts with approved class: " + sku)
        classifications[sku] = kind
    if set(products) != seen:
        raise ValueError("Incomplete catalog review")
    result = {"schema_version": 1, "source_sha256": EXPECTED_SOURCE_SHA,
              "store_id": STORE_ID, "reviewer": reviewer,
              "review_csv_sha256": hashlib.sha256(review_file.read_bytes()).hexdigest(),
              "item_classes": dict(sorted(classifications.items())),
              "blocked_item_codes": sorted(excluded),
              "excluded_pos": dict(sorted(excluded.items())),
              "class_counts": {kind: list(classifications.values()).count(kind)
                               for kind in sorted(CLASSES)},
              "applies_taxes": False}
    _private_write(output, result)
    return {"approved": len(classifications), "blocked": len(excluded),
            "class_counts": result["class_counts"],
            "mapping_file": str(output), "writes_to_destinations": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--prepare", type=Path)
    parser.add_argument("--approve", type=Path)
    parser.add_argument("--reviewer")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    products = load_source(args.source)
    if bool(args.prepare) == bool(args.approve):
        parser.error("Select exactly one of --prepare or --approve")
    if args.prepare:
        result = prepare(products, args.prepare)
    else:
        if not args.output or not args.reviewer:
            parser.error("--approve requires --output and --reviewer")
        result = approve(products, args.approve, args.output, args.reviewer)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
