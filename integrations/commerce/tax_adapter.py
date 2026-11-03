"""Provider-neutral tax calculation request boundary; no tax rules or network access.

A configured external adapter must resolve address-specific tax jurisdictions,
applicable food exemptions, nexus, fees and effective-dated rates. This module
ONLY validates request identity and binds a result to the approved product
classification. Nothing here computes an actual tax rate or remits tax.

Call get_quote with an authenticated, configured provider callable (typically
implemented in a future provider-specific integration). With no provider,
the request fails closed. Do not replace this with a hard-coded rate fallback.
"""
from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import json


_ALLOWED_CHANNELS = {"market", "pickup", "delivery", "shipping"}
_CLASSES = {"grocery_food", "cultivation_supply", "other_reviewed"}


def _required_string(value, label):
    if not isinstance(value, str) or not value.strip() or len(value) > 256:
        raise ValueError("Missing or invalid " + label)
    return value.strip()


def _decimal(value, label):
    if isinstance(value, bool):
        raise ValueError("Invalid " + label)
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("Invalid " + label) from exc
    if not number.is_finite() or number < 0:
        raise ValueError("Invalid " + label)
    return number


def _location(location):
    """Require delivery street address, not merely a ZIP, or exact market venue."""
    if not isinstance(location, dict):
        raise ValueError("Structured transaction location required")
    for field in ("street1", "city", "state", "postal_code", "country"):
        _required_string(location.get(field), "location." + field)
    if location["country"] != "US" or len(location["state"]) != 2:
        raise ValueError("Only reviewed US destinations are supported")
    # An exact street address is needed for boundary-specific district lookup.
    if not any(c.isdigit() for c in location["street1"]):
        raise ValueError("Physical street address required; ZIP-only is not adequate")
    return {k: location[k] for k in ("street1", "city", "state", "postal_code", "country")}


def build_request(order, classifications, source_sha):
    """Return source-bound, immutable tax request; never infer product taxability."""
    if source_sha != "0b4eec40a1cfd1d62551e2ac951a42dac21984f34ffb2d03f9aea697d1d713a8":
        raise ValueError("Tax classification source snapshot changed")
    if not isinstance(classifications, dict) or not classifications:
        raise ValueError("Approved tax classification mapping required")
    if not isinstance(order, dict):
        raise ValueError("Structured order required")
    for key in ("external_order_id", "provider", "site_key"):
        _required_string(order.get(key), key)
    channel = order.get("channel")
    if channel not in _ALLOWED_CHANNELS:
        raise ValueError("Explicit market/pickup/delivery/shipping channel required")
    try:
        event_date = date.fromisoformat(_required_string(order.get("transaction_date"), "transaction_date"))
    except ValueError as exc:
        raise ValueError("Valid transaction date required") from exc
    if order.get("currency") != "USD":
        raise ValueError("Only USD orders supported")
    destination = _location(order.get("location"))
    lines = order.get("lines")
    if not isinstance(lines, list) or not lines:
        raise ValueError("Nonempty order lines required")
    request_lines = []
    for i, line in enumerate(lines):
        if not isinstance(line, dict):
            raise ValueError("Invalid order line")
        code = _required_string(line.get("item_code"), "item_code")
        tax_class = classifications.get(code)
        if tax_class not in _CLASSES:
            raise ValueError("Missing owner-reviewed tax classification: " + code)
        qty = _decimal(line.get("quantity"), "quantity")
        unit = _decimal(line.get("unit_price"), "unit_price")
        if qty <= 0:
            raise ValueError("Positive quantity required")
        if unit != unit.quantize(Decimal("0.01")):
            raise ValueError("Unit price must be in cents")
        request_lines.append({
            "line_index": i, "item_code": code,
            "tax_class": tax_class, "quantity": str(qty),
            "unit_price": str(unit)})
    # Do not silently omit delivery fees, coupons, discounts or freight.
    if any(key in order for key in ("shipping_total", "discount_total", "fees", "discounts")):
        raise ValueError("Shipping/discount/fees require an explicitly mapped provider adapter")
    payload = {"schema_version": 1, "source_sha256": source_sha,
               "source_order": order["external_order_id"],
               "order_provider": order["provider"], "site_key": order["site_key"],
               "currency": "USD", "channel": channel,
               "transaction_date": event_date.isoformat(),
               "location": destination, "lines": request_lines}
    if channel == "market":
        payload["market_event_id"] = _required_string(order.get("market_event_id"), "market_event_id")
    payload["request_sha256"] = hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return payload


def get_quote(request, provider_name, provider=None):
    """Bind a real provider answer to the exact order request.

    Provider must be explicitly configured, and its authenticated transport
    supplied by the caller. Provider response rates are NOT authoritative
    until the provider is independently evaluated for destination correctness.
    """
    name = _required_string(provider_name, "provider_name")
    if provider is None or not callable(provider):
        raise ValueError("No configured jurisdiction tax provider")
    if not isinstance(request, dict) or not request.get("request_sha256"):
        raise ValueError("Compiled tax request required")
    result = provider(request)
    if not isinstance(result, dict):
        raise ValueError("Malformed tax provider result")
    if result.get("provider") != name or result.get("source_order") != request["source_order"]:
        raise ValueError("Tax provider/order identity mismatch")
    if result.get("request_sha256") != request["request_sha256"]:
        raise ValueError("Tax response is not bound to the reviewed request")
    if result.get("currency") != "USD" or result.get("channel") != request["channel"]:
        raise ValueError("Tax provider currency/channel mismatch")
    if len(result.get("lines", [])) != len(request["lines"]):
        raise ValueError("Tax provider returned wrong line count")
    for expected, actual in zip(request["lines"], result["lines"]):
        if (actual.get("line_index") != expected["line_index"] or
            actual.get("item_code") != expected["item_code"] or
            actual.get("tax_class") != expected["tax_class"] or
            _decimal(actual.get("quantity"), "quantity") !=
                _decimal(expected["quantity"], "quantity")):
            raise ValueError("Provider tax line identity/class drift")
    if not result.get("jurisdiction_evidence") or result.get("collection_status") == "pending":
        raise ValueError("Incomplete jurisdiction/nexus determination")
    if any(x in result for x in ("remittances", "payment_credit")):
        raise ValueError("Payments already remitted are separate from tax quotes")
    return result
