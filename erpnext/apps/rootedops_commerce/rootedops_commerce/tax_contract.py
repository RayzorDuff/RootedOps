"""Provider-neutral, fail-closed tax quote validation for commerce order drafts.

The provider resolves jurisdictions, taxable product classes, nexus and rates;
ERPNext validates monetary proof and posts explicitly reviewed tax rows.
No network calls, Tax Rules, tax-rate tables, filings or accounting writes.
"""
from collections import defaultdict
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")
ALLOWED_CHANNELS = {"market", "pickup", "delivery", "shipping"}
ALLOWED_CLASSES = {"grocery_food", "cultivation_supply", "other_reviewed"}
ALLOWED_COLLECTION = {"collect", "not_required", "pending"}


def _money(value):
    if isinstance(value, bool):
        raise ValueError("Boolean is not money")
    try:
        number = Decimal(str(value))
    except (ValueError, TypeError, InvalidOperation) as exc:
        raise ValueError("Invalid monetary value") from exc
    if not number.is_finite() or number < 0 or number != number.quantize(CENT):
        raise ValueError("Monetary values must be finite nonnegative cents")
    return number


def _decimal(value):
    if isinstance(value, bool):
        raise ValueError("Boolean is not numeric")
    try:
        number = Decimal(str(value))
    except (ValueError, TypeError, InvalidOperation) as exc:
        raise ValueError("Invalid decimal") from exc
    if not number.is_finite() or number < 0:
        raise ValueError("Finite nonnegative decimal required")
    return number


def _text(value, field):
    if not isinstance(value, str) or not value.strip() or len(value) > 256:
        raise ValueError("Missing or invalid " + field)
    return value.strip()


def validate_quote(quote, order_lines, currency, total):
    """Return expected ERP 'Actual' tax rows, never a remittance or filing credit.

    v1 quote contract:
      schema_version, provider, quote_id, source_order, currency, channel,
      location_ref, jurisdiction_evidence, collection_status, lines, components,
      tax_total, calculated_total.

    Every component is tied to line_index, exact jurisdiction and ERP account,
    with explicit taxable_base, rate_percent, tax_amount and taxability reason.
    Item classifications are supplied by a reviewed SKU mapping, not inferred
    from product names. The provider's account selection MUST be independently
    checked against the trusted ERPNext liability-account policy by the caller.
    """
    if not isinstance(quote, dict) or quote.get("schema_version") != 1:
        raise ValueError("Tax quote schema_version=1 required")
    for name in ("provider", "quote_id", "source_order", "location_ref",
                 "jurisdiction_evidence"):
        _text(quote.get(name), name)
    if quote.get("currency") != currency or currency != "USD":
        raise ValueError("Tax quote currency mismatch")
    if quote.get("channel") not in ALLOWED_CHANNELS:
        raise ValueError("Unknown tax sourcing channel")
    collection = quote.get("collection_status")
    if collection not in ALLOWED_COLLECTION:
        raise ValueError("Unknown collection determination")
    if collection == "pending":
        raise ValueError("Unknown nexus/location/taxability: defer order staging")
    if "remittances" in quote or "payment_credit" in quote:
        raise ValueError("Tax payments belong to separate remittance accounting")
    if any(k in quote for k in ("default_rate", "origin_rate", "tax_included")):
        raise ValueError("Unsupported inferred/default tax calculation")
    lines = quote.get("lines")
    if not isinstance(lines, list) or len(lines) != len(order_lines) or not lines:
        raise ValueError("Tax quote lines differ from reviewed order lines")
    for index, (tax_line, order_line) in enumerate(zip(lines, order_lines)):
        if not isinstance(tax_line, dict) or tax_line.get("line_index") != index:
            raise ValueError("Stable tax line_index required")
        if _text(tax_line.get("item_code"), "item_code") != order_line["item_code"]:
            raise ValueError("Tax quote item identity mismatch")
        if tax_line.get("tax_class") not in ALLOWED_CLASSES:
            raise ValueError("Unreviewed item tax class")
        if _decimal(tax_line.get("quantity")) != _decimal(order_line["qty"]):
            raise ValueError("Tax quote quantity mismatch")
        rate = _money(order_line["rate"])
        base = (_decimal(order_line["qty"]) * rate).quantize(CENT, rounding=ROUND_HALF_UP)
        if _money(tax_line.get("line_total")) != base:
            raise ValueError("Tax quote line total mismatch")
    components = quote.get("components")
    if not isinstance(components, list):
        raise ValueError("Explicit jurisdiction components required")
    per_account = defaultdict(lambda: Decimal("0"))
    seen = set()
    for part in components:
        if not isinstance(part, dict):
            raise ValueError("Malformed tax component")
        index = part.get("line_index")
        if type(index) is not int or not 0 <= index < len(lines):
            raise ValueError("Tax component must identify an order line")
        authority = _text(part.get("authority"), "authority")
        jurisdiction = _text(part.get("jurisdiction_id"), "jurisdiction_id")
        account = _text(part.get("account_head"), "account_head")
        _text(part.get("taxability"), "taxability")
        key = (index, jurisdiction, authority, account)
        if key in seen:
            raise ValueError("Duplicate jurisdiction/line tax component")
        seen.add(key)
        base = _money(part.get("taxable_base"))
        if base > _money(lines[index]["line_total"]):
            raise ValueError("Taxable base exceeds line amount")
        rate = _decimal(part.get("rate_percent"))
        if rate > 100:
            raise ValueError("Impossible percentage")
        amount = _money(part.get("tax_amount"))
        calculated = (base * rate / 100).quantize(CENT, rounding=ROUND_HALF_UP)
        if amount != calculated:
            raise ValueError("Jurisdiction tax component arithmetic mismatch")
        if collection == "not_required" and amount:
            raise ValueError("No-collection determination cannot charge tax")
        per_account[account] += amount
    tax_total = sum(per_account.values(), Decimal("0"))
    if tax_total != _money(quote.get("tax_total")):
        raise ValueError("Provider quote tax total mismatch")
    merchandise = sum(
        (_money(line["line_total"]) for line in lines), Decimal("0"))
    if merchandise + tax_total != _money(quote.get("calculated_total")):
        raise ValueError("Tax quote gross total mismatch")
    if _money(total) != _money(quote["calculated_total"]):
        raise ValueError("Source order total differs from tax quote")
    if collection == "not_required" and components:
        if any(_money(x["taxable_base"]) for x in components):
            raise ValueError("No collection must not claim a taxable base")
    return [
        {"charge_type": "Actual", "account_head": account,
         "description": "Jurisdiction tax from reviewed provider quote",
         "tax_amount": str(amount)}
        for account, amount in sorted(per_account.items())
        if amount
    ]


def validate_erp_taxes(expected, draft_taxes):
    """Match the quote-derived tax liability without trusting external tax rows."""
    if not isinstance(draft_taxes, list):
        raise ValueError("Reviewed tax rows required")
    actual = defaultdict(lambda: Decimal("0"))
    for row in draft_taxes:
        if not isinstance(row, dict) or set(row) - {
            "charge_type", "account_head", "description", "tax_amount"
        } or row.get("charge_type") != "Actual":
            raise ValueError("Unsupported ERP actual-tax row")
        account = _text(row.get("account_head"), "ERP tax account")
        actual[account] += _money(row.get("tax_amount"))
    required = {x["account_head"]: _money(x["tax_amount"]) for x in expected}
    if {k: v for k, v in actual.items() if v} != required:
        raise ValueError("ERP tax rows must exactly match validated quote")
    if any(v == 0 for v in actual.values()):
        raise ValueError("Zero tax rows require explicit omission")
    return True
