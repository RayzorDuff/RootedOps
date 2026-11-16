"""Post one sandbox capture into ERP clearing in one Frappe transaction."""
import hmac
import json

import frappe

from rootedops_commerce.contract import mapping_key
from rootedops_commerce.external_receipt import canonical, finish, lock_receipt
from rootedops_commerce.order_service import _authorized, attach_financial_documents
from rootedops_commerce.tax_contract import _money

STAGING = {'erp-test.danks.store': 'shop-test.danks.store',
           'erp-test2.danks.store': 'shop-test2.danks.store'}


def verified_config(data, signature):
    config = frappe.conf.get('commerce_clover_capture_pilot') or {}
    secret = config.get('evidence_hmac') or ''
    if (config.get('enabled') is not True or len(secret) < 32
            or STAGING.get(frappe.local.site) != data.get('site_key')
            or config.get('merchant_id') != data.get('merchant_id')
            or not config.get('merchant_id')):
        raise ValueError('Clover capture posting requires the matched sandbox pilot')
    proof = hmac.digest(secret.encode(), canonical(data), 'sha256').hex()
    if not isinstance(signature, str) or not hmac.compare_digest(proof, signature):
        raise ValueError('Payment evidence is not authenticated')
    if (data.get('processor') != 'clover' or data.get('provider_environment') != 'sandbox'
            or data.get('verification') != 'verified_adapter' or data.get('state') != 'captured'
            or data.get('processor_reference_type') != 'clover_ecommerce_charge'
            or data.get('provider') != 'woocommerce' or not data.get('payment_id')
            or _money(data.get('refunded_amount'))):
        raise ValueError('Only verified unrefunded sandbox captures may post')
    return config


@frappe.whitelist(methods=['POST'])
def reconcile_capture(payload, signature):
    _authorized(financial=True)
    data = frappe.parse_json(payload)
    config = verified_config(data, signature)
    source = {key: data[key] for key in ('provider', 'site_key', 'external_order_id')}
    key = mapping_key(*source.values())
    receipt = lock_receipt('clover_capture', [data['provider_environment'], data['merchant_id'],
                           data['payment_id']], data)
    state = frappe.get_doc('Commerce Order State', key, for_update=True)
    state.check_permission('write')
    order = frappe.get_doc('Sales Order', state.sales_order, for_update=True)
    order.check_permission('read')
    amount = _money(data['captured_amount'])
    if (not amount or order.company != config['company'] or order.currency != data['currency']
            or _money(order.grand_total) != amount or order.docstatus != 1
            or state.status not in ('processing', 'completed')):
        raise ValueError('Active submitted sale, exact capture total and reviewed company required')
    clearing = frappe.get_doc('Account', config['clearing_account'])
    clearing.check_permission('read')
    if (clearing.company != order.company or clearing.account_currency != order.currency
            or clearing.is_group or clearing.disabled or clearing.root_type != 'Asset'
            or clearing.account_type not in ('Bank', 'Cash')):
        raise ValueError('Enabled company/currency Clover clearing account required')
    if receipt.result:
        prior = json.loads(receipt.result)
        if [prior['sales_invoice'], prior['payment_entry']] != [state.sales_invoice, state.payment_entry]:
            raise ValueError('ERP capture references require reconciliation')
        _verify_clearing(prior['payment_entry'], clearing.name, data)
        attach_financial_documents(dict(source, sales_invoice=state.sales_invoice, payment_entry=state.payment_entry))
        return prior
    if state.sales_invoice or state.payment_entry:
        if not state.sales_invoice or not state.payment_entry:
            raise ValueError('Partial pre-existing ERP links require reviewed reconciliation')
        invoice_name, payment_name = state.sales_invoice, state.payment_entry
        _verify_clearing(payment_name, clearing.name, data)
    else:
        from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
        from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice

        invoice = make_sales_invoice(order.name)
        invoice.update_stock = 0
        invoice.posting_date = data['posting_date']
        invoice.set_posting_time = 1
        invoice.insert()
        if _money(invoice.grand_total) != amount:
            raise ValueError('Native invoice total differs from verified capture')
        invoice.submit()
        payment = get_payment_entry('Sales Invoice', invoice.name, bank_account=clearing.name)
        payment.posting_date = data['posting_date']
        payment.reference_date = data['posting_date']
        payment.reference_no = data['payment_id']
        payment.paid_to = clearing.name
        payment.insert()
        payment.submit()
        invoice_name, payment_name = invoice.name, payment.name
    attached = attach_financial_documents(dict(source, sales_invoice=invoice_name, payment_entry=payment_name))
    return finish(receipt, {key: attached[key] for key in ('sales_order', 'sales_invoice', 'payment_entry')})


def _verify_clearing(name, account, data):
    payment = frappe.get_doc('Payment Entry', name)
    payment.check_permission('read')
    if payment.paid_to != account or payment.reference_no != data['payment_id']:
        raise ValueError('ERP receipt processor identity or clearing account differs')
