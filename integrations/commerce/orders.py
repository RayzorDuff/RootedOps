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


def normalize_woo(raw, signature, secrets, site, mappings, gateways):
    event_id = authenticate(raw, signature, secrets)
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate JSON key')
            result[key] = value
        return result
    order = json.loads(raw, object_pairs_hook=unique_object)
    if not site or not str(order['id']).isdigit() or int(order['id']) <= 0:
        raise ValueError('Site and stable Woo order ID required')
    statuses = {'pending', 'on-hold', 'processing', 'completed', 'cancelled', 'failed', 'refunded'}
    if order['status'] not in statuses:
        raise ValueError('Unknown order status requires review')
    # Woo's GMT field has no offset; do not accept local timestamps.
    modified = datetime.strptime(order['date_modified_gmt'], '%Y-%m-%dT%H:%M:%S').replace(tzinfo=timezone.utc)
    currency = order['currency']
    if not isinstance(currency, str) or len(currency) != 3 or not currency.isalpha() or currency != currency.upper():
        raise ValueError('Explicit ISO currency required')
    processor = gateways[order['payment_method']]
    if processor != 'clover':
        raise ValueError('Only reviewed Clover gateway supported in this milestone')
    lines, seen = [], set()
    for line in order['line_items']:
        line_id = str(line['id'])
        if line_id in seen:
            raise ValueError('Duplicate Woo line ID')
        seen.add(line_id)
        # Numeric Woo IDs AND exact SKU must agree with the approved map.
        key = str(line.get('variation_id') or line['product_id'])
        mapping = mappings[key]
        if mapping['sku'] != line['sku']:
            raise ValueError('Woo identity/SKU drift')
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
    return {'schema_version': 1, 'provider': 'woocommerce', 'site_key': site,
            'external_order_id': str(order['id']), 'event_id': event_id,
            'revision': int(modified.timestamp()), 'status': order['status'],
            'currency': order['currency'], 'total': total, 'lines': lines, 'refunds': refunds,
            'payment_processor': processor, 'processor_payment_id': order.get('transaction_id') or None,
            'reconciliation_status': 'unverified', 'fulfillment_requested': order['status'] == 'completed'}


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
