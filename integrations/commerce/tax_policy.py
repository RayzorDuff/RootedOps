"""Load owner-approved immutable tax classes; reject generic POS at ingress.

Pure validation; never posts transactions, applies tax rates, or changes catalog.
"""
import json
from pathlib import Path

SOURCE_SHA = "0b4eec40a1cfd1d62551e2ac951a42dac21984f34ffb2d03f9aea697d1d713a8"
CLASSES = {"grocery_food", "cultivation_supply", "other_reviewed"}


def validate_policy(document):
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        raise ValueError("Approved tax classification schema required")
    if document.get("source_sha256") != SOURCE_SHA or document.get("store_id") != "95802503":
        raise ValueError("Approved tax classification source mismatch")
    if document.get("applies_taxes") is not False:
        raise ValueError("Classifications may not activate tax collection")
    approved = document.get("item_classes")
    blocked = document.get("blocked_item_codes")
    details = document.get("excluded_pos")
    if (not isinstance(approved, dict) or not isinstance(blocked, list)
            or not isinstance(details, dict)):
        raise ValueError("Missing reviewed class or blocked POS identities")
    if len(approved) != 119 or len(blocked) != 13 or len(set(blocked)) != 13:
        raise ValueError("Incomplete tax classification: expect 119 approved and 13 blocked")
    if (set(approved) & set(blocked) or set(details) != set(blocked)
            or any(not isinstance(k, str) or not k for k in list(approved) + blocked)
            or any(v not in CLASSES for v in approved.values())):
        raise ValueError("Invalid approved/blocked item identity")
    if {c: list(approved.values()).count(c) for c in sorted(CLASSES)} != {
            "grocery_food": 40, "cultivation_supply": 78, "other_reviewed": 1}:
        raise ValueError("Owner-reviewed class totals differ")
    if document.get("class_counts") != {
            c: list(approved.values()).count(c) for c in sorted(CLASSES)}:
        raise ValueError("Stored class count mismatch")
    if not document.get("review_csv_sha256") or not document.get("reviewer"):
        raise ValueError("Missing review provenance")
    if any(not isinstance(details[k], dict) or not details[k].get("reason")
           or not details[k].get("source_product_id") for k in blocked):
        raise ValueError("Missing explicit generic POS exclusion evidence")
    return {"approved": dict(approved), "blocked": frozenset(blocked)}


def load_policy(path):
    filename = Path(path).expanduser().resolve(strict=True)
    if not filename.is_file() or filename.stat().st_mode & 0o077:
        raise ValueError("Approved tax mapping must be a private file (0600)")
    if filename.parent.stat().st_mode & 0o077:
        raise ValueError("Approved tax mapping directory must be private (0700)")
    return validate_policy(json.loads(filename.read_text(encoding="utf-8")))


def require_approved_item(code, policy):
    if not isinstance(code, str) or not code:
        raise ValueError("Missing authoritative ERP Item code")
    if code in policy["blocked"]:
        raise ValueError("Generic POS item prohibited from tax-calculated orders")
    tax_class = policy["approved"].get(code)
    if tax_class not in CLASSES:
        raise ValueError("Unapproved ERP Item for tax-calculated order")
    return tax_class
