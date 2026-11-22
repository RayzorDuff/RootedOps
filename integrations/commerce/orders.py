"""Authenticated Woo order normalization and Clover reconciliation contracts.

No HTTP listener, merchant requests, accounting writes or inventory writes.
The authenticated raw bytes must reach this boundary before JSON parsing.
"""
import base64
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import hmac
import json
from reviewed_catalog import money


def authenticate(raw, signature, secrets):
    if not isinstance(raw, bytes) or len(raw) > 2 * 1024 * 1024:
        raise ValueError('Raw webhook body required, maximum 2 MiB')
    if not secrets or any(not isinstance(s, str) or len(s) < 32 for s in secrets):
        raise ValueError('Configure strong current/previous webhook secrets')
    try:
        provided = base64.b64decode(signature, validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError('Malformed webhook signature') from exc
    valid = False
    for secret in secrets:  # Evaluate all rotation candidates.
        valid |= hmac.compare_digest(provided, hmac.digest(secret.encode(), raw, 'sha256'))
    if not valid:
        raise ValueError('Invalid webhook signature')
    return hashlib.sha256(raw).hexdigest()


class OrderReview(ValueError):
    """A signed order needs a reviewed mapping or commercial decision."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


def woo_source(raw, site, event_id):
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate JSON key')
            result[key] = value
        return result

    order = json.loads(raw, object_pairs_hook=unique_object)
    if not site or type(order['id']) is not int or not 0 < order['id'] < 2**63:
        raise ValueError('Site and stable numeric Woo order ID required')
    # Woo's GMT field has no offset. Arrival time cannot order same-second changes.
    modified = datetime.strptime(order['date_modified_gmt'], '%Y-%m-%dT%H:%M:%S').replace(tzinfo=timezone.utc)
    identity = {'provider': 'woocommerce', 'site_key': site, 'external_order_id': str(order['id']),
                'event_id': event_id, 'revision': int(modified.timestamp())}
    return order, identity


def normalize_woo(raw, signature, secrets, site, mappings, gateways, tax_policy=None):
    event_id = authenticate(raw, signature, secrets)
    order, identity = woo_source(raw, site, event_id)
    return normalize_order(order, identity, mappings, gateways, tax_policy=tax_policy)


def normalize_order(order, identity, mappings, gateways, *, tax_policy=None, pilot_items=None, reviewed_mapping=False, clover_capture_pilot=False, production=False, cash_receipt_pilot=False):
    statuses = {'pending', 'on-hold', 'processing', 'completed', 'cancelled', 'failed', 'refunded'}
    if order['status'] not in statuses:
        raise OrderReview('order_status_review')
    currency = order['currency']
    if not isinstance(currency, str) or len(currency) != 3 or not currency.isalpha() or currency != currency.upper():
        raise ValueError('Explicit ISO currency required')
    processor = gateways.get(order['payment_method'])
    if pilot_items is None:
        if processor != 'clover':
            raise OrderReview('gateway_review')
    elif processor == 'cash':
        if not reviewed_mapping or not cash_receipt_pilot or order.get('transaction_id'):
            raise OrderReview('cash_tender_review')
    elif processor == 'clover':
        if not reviewed_mapping or not clover_capture_pilot:
            raise OrderReview('gateway_review')
    elif (processor != 'manual_unpaid' or order['status'] not in ('pending', 'on-hold', 'cancelled')
          or order.get('transaction_id') or order.get('date_paid_gmt') or order.get('refunds')):
        raise OrderReview('gateway_review')
    lines, seen, amounts, sources = [], set(), {}, {}
    for line in order['line_items']:
        if type(line['id']) is not int or not 0 < line['id'] < 2**63:
            raise ValueError('Stable numeric Woo line ID required')
        line_id = str(line['id'])
        if line_id in seen:
            raise ValueError('Duplicate Woo line ID')
        seen.add(line_id)
        # Numeric Woo IDs AND exact SKU must agree with the approved map.
        product_id, variation_id = line['product_id'], line.get('variation_id', 0)
        if (type(product_id) is not int or not 0 < product_id < 2**63
                or type(variation_id) is not int or not 0 <= variation_id < 2**63):
            raise ValueError('Invalid Woo product or variation ID')
        mapping = mappings.get(str(variation_id or product_id))
        if mapping is None:
            raise OrderReview('item_unmapped')
        if not isinstance(mapping, dict) or not {
                'sku', 'erp_item_code', 'ecommerce_id'}.issubset(mapping):
            raise OrderReview('item_mapping_review')
        if mapping.get('enabled', True) is not True:
            raise OrderReview('item_disabled')
        if (not mapping['sku'] or mapping['sku'] != line['sku']
                or not mapping['erp_item_code'] or type(mapping['ecommerce_id']) is not int
                or mapping['ecommerce_id'] <= 0
                or ('product_id' in mapping and mapping['product_id'] != product_id)):
            raise OrderReview('item_mapping_review')
        if pilot_items is not None:
            if mapping['erp_item_code'] not in pilot_items:
                raise OrderReview('item_mapping_review')
            amounts[line_id] = (money(line['total']) if reviewed_mapping else
                                pilot_amount(line, ('subtotal_tax', 'total_tax'), subtotal=True))
            sources[line_id] = {'product_id': str(product_id),
                                'variation_id': str(variation_id) if variation_id else None,
                                'sku': line['sku']}
        if tax_policy is not None:
            # A generic amount-based POS button is not a real product.
            # Check the mapped ERP identity, not the untrusted Woo item label.
            from tax_policy import require_approved_item
            require_approved_item(mapping['erp_item_code'], tax_policy)
        qty = line['quantity']
        if type(qty) is not int or qty <= 0:
            raise ValueError('Positive integer operational quantity required')
        lines.append({'line_id': line_id, 'ecommerce_id': mapping['ecommerce_id'],
                      'erp_item_code': mapping['erp_item_code'], 'quantity': qty})
    if not lines:
        raise ValueError('Empty Woo order')
    refunds, refund_ids = [], set()
    for refund in order.get('refunds', []):
        rid = str(refund['id'])
        if rid in refund_ids:
            raise ValueError('Duplicate refund identity')
        refund_ids.add(rid)
        amount = Decimal(str(refund['total']))
        if not amount.is_finite() or amount > 0:
            raise ValueError('Woo refund total must be nonpositive')
        refunds.append({'external_refund_id': rid, 'amount': money(-amount)})
    total = money(order['total'])
    if sum(Decimal(r['amount']) for r in refunds) > Decimal(total):
        raise ValueError('Refunds exceed order total')
    if order['status'] == 'refunded' and sum(Decimal(r['amount']) for r in refunds) != Decimal(total):
        raise ValueError('Full-refund status requires complete refund snapshot')
    result = {'schema_version': 1, **identity, 'status': order['status'],
            'currency': order['currency'], 'total': total, 'lines': lines, 'refunds': refunds,
            'payment_processor': processor, 'processor_payment_id': order.get('transaction_id') or None,
            'reconciliation_status': 'unverified', 'fulfillment_requested': order['status'] == 'completed'}

    if 'customer_id' in order:
        customer_id = order['customer_id']
        if type(customer_id) is not int or not 0 <= customer_id < 2**63:
            raise ValueError('Invalid Woo order customer ID')
        result['external_customer_id'] = str(customer_id) if customer_id else None
    if pilot_items is not None:
        if 'external_customer_id' not in result:
            raise OrderReview('customer_mapping_review')
        if reviewed_mapping:
            if production:
                result['source_created_gmt'] = order['date_created_gmt']
            result.update(order_intake_mode='reviewed_mapping', line_sources=sources,
                          commercial=woo_commercial(order, amounts))
            return result
        for key in ('shipping_lines', 'fee_lines', 'coupon_lines', 'tax_lines'):
            if order[key]:
                raise OrderReview('commercial_review')
        expected = pilot_amount(order, ('discount_total', 'discount_tax', 'shipping_total',
                                        'shipping_tax', 'cart_tax', 'total_tax'))
        if sum(Decimal(value) for value in amounts.values()) != Decimal(expected):
            raise OrderReview('commercial_review')
        result.update(order_intake_mode='unpaid_pilot', line_amounts=amounts, line_sources=sources)
    return result


def woo_commercial(order, amounts):
    from draft_mapping import cents
    if order['fee_lines'] or order.get('prices_include_tax') is not False:
        raise OrderReview('commercial_review')
    subtotal = sum(cents(line['subtotal']) for line in order['line_items'])
    net = sum(cents(value) for value in amounts.values())
    if (any(cents(line['subtotal']) < cents(line['total']) for line in order['line_items'])
            or subtotal - net != cents(order['discount_total'])):
        raise OrderReview('commercial_review')
    shipping, tax = cents(order['shipping_total']), cents(order['total_tax'])
    if (shipping != sum(cents(row['total']) for row in order['shipping_lines'])
            or cents(order['shipping_tax']) != sum(cents(row['total_tax']) for row in order['shipping_lines'])
            or cents(order['cart_tax']) != sum(cents(row['total_tax']) for row in order['line_items'])
            or tax != cents(order['cart_tax']) + cents(order['shipping_tax'])
            or cents(order['total']) != net + shipping + tax):
        raise OrderReview('commercial_review')
    address = order.get('shipping') or {}
    if not address.get('country'):
        address = order.get('billing') or {}
    location = [str(address.get(key) or '').strip().upper() for key in ('country', 'state', 'postcode', 'city')]
    return {'line_totals': amounts, 'shipping': str(shipping), 'tax': str(tax),
            'order_date': datetime.strptime(order['date_created_gmt'], '%Y-%m-%dT%H:%M:%S').date().isoformat(),
            'destination': hashlib.sha256(json.dumps(location).encode()).hexdigest()}


def pilot_amount(values, zero_fields, *, subtotal=False):
    total = money(values['total'])
    if (any(Decimal(money(values[key])) != 0 for key in zero_fields)
            or subtotal and Decimal(money(values['subtotal'])) != Decimal(total)):
        raise OrderReview('commercial_review')
    return total


def reconcile_clover(order, evidence):
    """A Woo paid status is not proof of capture. Require verified gateway evidence.

    Evidence must be fetched/verified by an eventual merchant adapter, never copied
    from an untrusted request. Matching by amount/time alone is prohibited.
    """
    if evidence['verification'] != 'verified_adapter' or evidence['processor'] != 'clover':
        raise ValueError('Verified Clover adapter evidence required')
    if evidence['site_key'] != order['site_key'] or evidence['external_order_id'] != order['external_order_id']:
        raise ValueError('Order/site evidence mismatch')
    if not order.get('processor_payment_id') or evidence['payment_id'] != order['processor_payment_id']:
        raise ValueError('Exact processor transaction identity required')
    if evidence['currency'] != order['currency'] or Decimal(money(evidence['captured_amount'])) != Decimal(money(order['total'])):
        raise ValueError('Capture currency/amount mismatch')
    if evidence['state'] != 'captured':
        raise ValueError('Authorization/pending/failure is not captured payment')
    refunds = sum(Decimal(money(r['amount'])) for r in order['refunds'])
    if Decimal(money(evidence['refunded_amount'])) != refunds:
        raise ValueError('Refund reconciliation mismatch')
    return {'status': 'matched', 'processor': 'clover', 'payment_id': evidence['payment_id'],
            'captured_amount': money(evidence['captured_amount']), 'refunded_amount': money(refunds),
            'currency': order['currency'], 'create_invoice': False, 'create_payment_entry': False}
