"""Post a separately confirmed MP cash receipt; never infer payment from dispatch."""
from copy import deepcopy
from datetime import datetime
import hashlib
import hmac
import json
import uuid

import frappe

from rootedops_commerce.contract import mapping_key
from rootedops_commerce.external_receipt import canonical, finish, lock_receipt
from rootedops_commerce.order_service import _authorized, _attach_financial_documents, check_draft_records, validate_draft
from rootedops_commerce.tax_contract import _money


def authorize(data, signature):
    config = frappe.conf.get('commerce_cash_accounting') or {}
    secret = config.get('evidence_hmac') or ''
    source = '|'.join(str(data.get(k) or '') for k in ('provider', 'site_key', 'external_order_id'))
    approval = (config.get('approved_orders') or {}).get(source) or {}
    if (config.get('enabled') is not True or len(secret) < 32 or approval.get('enabled') is not True
            or data.get('processor') != 'cash' or data.get('state') != 'received'
            or data.get('verification') != 'mp_operator_receipt' or not data.get('operator')
            or data.get('operator') == 'system' or data.get('provider') not in ('ecwid', 'woocommerce')):
        raise ValueError('Enabled cash accounting, reviewed source and explicit operator receipt required')
    proof = hmac.digest(secret.encode(), canonical(data), 'sha256').hex()
    if not isinstance(signature, str) or not hmac.compare_digest(proof, signature):
        raise ValueError('Cash receipt evidence is not authenticated')
    if approval.get('source_fingerprint') != data.get('source_fingerprint'):
        raise ValueError('Cash source snapshot differs from reviewed sale')
    uuid.UUID(data['receipt_id'])
    datetime.fromisoformat(data['received_at'].replace('Z', '+00:00'))
    if _money(data['amount']) <= 0 or data.get('refunded_amount', '0.00') != '0.00':
        raise ValueError('Positive unrefunded full cash receipt required')
    if frappe.local.site == 'erp.danks.store':
        allowed = {'ecwid': 'dank_mushrooms', 'woocommerce': 'danks.store'}
        if data['site_key'] != allowed[data['provider']] or approval.get('stock_authority') != 'mushroomprocess':
            raise ValueError('Reviewed production source and MP stock boundary required')
        if not approval.get('tax_quote'):
            raise ValueError('Reviewed destination tax quote required for production cash sale')
    elif frappe.local.site not in ('erp-test.danks.store', 'erp-test2.danks.store'):
        raise ValueError('Unreviewed ERP destination')
    return config, approval


def _verify_result(result, data, account):
    invoice = frappe.get_doc('Sales Invoice', result['sales_invoice'])
    payment = frappe.get_doc('Payment Entry', result['payment_entry'])
    for doc in (invoice, payment):
        doc.check_permission('read')
    if (invoice.docstatus != 1 or invoice.is_return or invoice.update_stock
            or payment.docstatus != 1 or payment.paid_to != account
            or payment.reference_no != 'mp-cash:' + data['receipt_id']
            or _money(payment.received_amount) != _money(data['amount'])):
        raise ValueError('Cash financial documents require reconciliation')
    return _attach_financial_documents({k: data[k] for k in ('provider', 'site_key', 'external_order_id')} | result)


@frappe.whitelist(methods=['POST'])
def reconcile_receipt(payload, signature):
    _authorized(financial=True)
    data = frappe.parse_json(payload)
    config, approval = authorize(data, signature)
    values = deepcopy(approval['reviewed_draft'])
    event = dict(provider=data['provider'], site_key=data['site_key'], external_order_id=data['external_order_id'],
                 currency=data['currency'], total=data['amount'], lines=data['lines'])
    if approval.get('tax_quote'):
        event['tax_quote'] = approval['tax_quote']
    commercial = data.get('commercial')
    if commercial is not None:
        expected_amounts = {}
        for line in data['lines']:
            code = line['erp_item_code']
            expected_amounts[code] = expected_amounts.get(code, 0) + _money(commercial['line_totals'][line['line_id']])
        shipping = _money(commercial['shipping'])
        if shipping:
            shipping_code = frappe.conf.get('commerce_order_shipping_item')
            if not shipping_code or shipping_code in expected_amounts:
                raise ValueError('Separate reviewed shipping Item required')
            shipping_item = frappe.get_doc('Item', shipping_code)
            shipping_item.check_permission('read')
            if shipping_item.is_stock_item or shipping_item.disabled or shipping_item.has_variants:
                raise ValueError('Enabled nonstock shipping Item required')
            expected_amounts[shipping_code] = shipping
            event['lines'] = list(data['lines']) + [dict(erp_item_code=shipping_code, quantity=1)]
        actual_amounts = {}
        for line in values['items']:
            code = line['item_code']
            actual_amounts[code] = actual_amounts.get(code, 0) + _money(line['rate']) * line['qty']
        if actual_amounts != expected_amounts or sum(_money(t['tax_amount']) for t in values.get('taxes', [])) != _money(commercial['tax']):
            raise ValueError('Reviewed cash prices, shipping or tax differ from source')
    validate_draft(values, event)
    check_draft_records(values)
    if values['company'] != config['company']:
        raise ValueError('Reviewed cash company differs from sale')
    account = frappe.get_doc('Account', config['cash_account'])
    account.check_permission('read')
    if (account.company != values['company'] or account.account_currency != data['currency']
            or account.disabled or account.is_group or account.root_type != 'Asset'
            or account.account_type not in ('Cash', 'Bank')):
        raise ValueError('Reviewed enabled cash/undeposited-funds account required')
    receipt = lock_receipt('mp_cash_receipt', [data['provider'], data['site_key'], data['receipt_id']], dict(data, reviewed_draft=values, cash_account=account.name, posting_date=approval['posting_date']))
    if receipt.result:
        prior = json.loads(receipt.result)
        _verify_result(prior, data, account.name)
        return prior
    key = mapping_key(data['provider'], data['site_key'], data['external_order_id'])
    if frappe.db.exists('Commerce Order State', key):
        state = frappe.get_doc('Commerce Order State', key, for_update=True)
        state.check_permission('write')
        if state.status in ('cancelled', 'failed', 'refunded'):
            raise ValueError('Cancelled/refunded sale requires review')
        order = frappe.get_doc('Sales Order', state.sales_order, for_update=True)
        order.check_permission('read')
        if (state.sales_invoice or state.payment_entry):
            if not state.sales_invoice or not state.payment_entry:
                raise ValueError('Partial pre-existing financial references require review')
            prior = dict(sales_order=order.name, sales_invoice=state.sales_invoice, payment_entry=state.payment_entry)
            _verify_result(prior, data, account.name)
            return finish(receipt, prior)
        if (order.customer != values['customer'] or order.company != values['company']
                or order.currency != data['currency'] or order.docstatus != 1
                or _money(order.grand_total) != _money(data['amount'])):
            raise ValueError('Submitted exact reviewed sale required')
        actual = {}
        for line in order.items:
            qty, amount = actual.get(line.item_code, (0, 0))
            actual[line.item_code] = (qty + line.qty, amount + _money(line.amount))
        expected = {}
        for line in values['items']:
            qty, amount = expected.get(line['item_code'], (0, 0))
            expected[line['item_code']] = (qty + line['qty'], amount + _money(line['rate']) * line['qty'])
        actual_tax = [(r.charge_type, r.account_head, _money(r.tax_amount)) for r in order.taxes]
        expected_tax = [(r['charge_type'], r['account_head'], _money(r['tax_amount'])) for r in values.get('taxes', [])]
        if actual != expected or actual_tax != expected_tax:
            raise ValueError('Existing ERP sale line quantities differ')
    else:
        if data['provider'] == 'woocommerce':
            raise ValueError('Wait for signed Woo intake and submitted reviewed Sales Order')
        # Ecwid cash sales may predate Woo intake. Exact source approval creates
        # the native operational sale, with no customer/catalog reimport.
        order = frappe.get_doc(dict(values, doctype='Sales Order')).insert()
        fingerprint = hashlib.sha256(json.dumps(values, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        state = frappe.get_doc(dict(doctype='Commerce Order State', source_key=key,
                provider=data['provider'], site_key=data['site_key'], external_order_id=data['external_order_id'],
                revision=1, status='processing', draft_hash=fingerprint, sales_order=order.name)).insert()
        order.submit()
    from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
    from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice
    invoice = make_sales_invoice(order.name)
    invoice.update_stock = 0
    invoice.posting_date = approval['posting_date']
    invoice.set_posting_time = 1
    invoice.insert()
    if _money(invoice.grand_total) != _money(data['amount']):
        raise ValueError('Native cash invoice total differs from receipt')
    invoice.submit()
    payment = get_payment_entry('Sales Invoice', invoice.name, bank_account=account.name)
    payment.posting_date = approval['posting_date']
    payment.reference_date = approval['posting_date']
    payment.reference_no = 'mp-cash:' + data['receipt_id']
    payment.paid_to = account.name
    if config.get('mode_of_payment'):
        payment.mode_of_payment = config['mode_of_payment']
    payment.insert()
    payment.submit()
    result = dict(sales_order=order.name, sales_invoice=invoice.name, payment_entry=payment.name)
    _verify_result(result, data, account.name)
    return finish(receipt, result)
