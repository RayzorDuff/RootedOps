"""Record an authenticated MP fulfillment receipt without ERP stock posting."""
import hmac
import json

import frappe

from rootedops_commerce.clover_payment import STAGING
from rootedops_commerce.contract import mapping_key
from rootedops_commerce.external_receipt import canonical, finish, lock_receipt


def add_quantities(plan, already_shipped, lines):
    if not isinstance(lines, list) or not lines:
        raise ValueError('Committed shipment line quantities required')
    next_counts = dict(already_shipped)
    seen = set()
    for row in lines:
        line_id = row['line_id']
        qty = row['quantity']
        expected = plan.get(line_id)
        if (line_id in seen or not expected or type(qty) is not int or qty <= 0
                or row['item_code'] != expected['item_code']):
            raise ValueError('Shipment line does not match the staged Woo line')
        seen.add(line_id)
        updated = next_counts.get(line_id, 0) + qty
        if updated > expected['quantity']:
            raise ValueError('Shipment exceeds the staged Woo line quantity')
        next_counts[line_id] = updated
    return next_counts


@frappe.whitelist(methods=['POST'])
def acknowledge_shipment(payload, signature):
    config = frappe.conf.get('commerce_mp_fulfillment_pilot') or {}
    secret = config.get('movement_hmac') or ''
    data = frappe.parse_json(payload)
    if (config.get('enabled') is not True or len(secret) < 32
            or data.get('provider') != 'woocommerce'
            or STAGING.get(frappe.local.site) != data.get('site_key')
            or not data.get('reference')):
        raise ValueError('Matched staging MP fulfillment pilot required')
    if not {'System Manager', 'Accounts Manager'} & set(frappe.get_roles()):
        frappe.throw('Commerce fulfillment role required', frappe.PermissionError)
    expected = hmac.digest(secret.encode(), canonical(data), 'sha256').hex()
    if not isinstance(signature, str) or not hmac.compare_digest(expected, signature):
        raise ValueError('Shipment proof is not authenticated')
    key = mapping_key(data['provider'], data['site_key'], data['external_order_id'])
    state = frappe.get_doc('Commerce Order State', key, for_update=True)
    state.check_permission('write')
    order = frappe.get_doc('Sales Order', state.sales_order)
    order.check_permission('read')
    if (order.docstatus != 1 or data['sales_order'] != order.name or not state.fulfillment_line_map
            or not state.sales_invoice or not state.payment_entry):
        raise ValueError('Submitted linked commercial order and financial references required')
    receipt = lock_receipt('mp_shipment', [data['site_key'], data['reference']], data)
    if receipt.result:
        return json.loads(receipt.result)
    plan = json.loads(state.fulfillment_line_map)
    shipped = add_quantities(plan, json.loads(state.fulfilled_quantities or '{}'), data['lines'])
    state.fulfilled_quantities = canonical(shipped).decode()
    state.save()
    complete = all(shipped.get(key, 0) == line['quantity'] for key, line in plan.items())
    return finish(receipt, dict(status='fulfilled' if complete else 'partial',
                                shipment_receipt=receipt.name, sales_order=order.name))
