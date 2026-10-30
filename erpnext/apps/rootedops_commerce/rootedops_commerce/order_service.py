"""Opt-in operational order drafts and explicit existing financial-document links.

Never submit documents or move stock based on a storefront status. Frappe POST
provides the transaction; callers must retry unique-key conflicts idempotently.
"""
from copy import deepcopy
import hashlib
import json
from decimal import Decimal
import frappe
from rootedops_commerce.contract import mapping_key


def _authorized(financial=False):
    if not frappe.conf.get('commerce_order_integration_enabled'):raise ValueError('Order integration disabled')
    roles={'System Manager','Accounts Manager'} if financial else {'System Manager','Sales Manager'}
    if not roles & set(frappe.get_roles()):frappe.throw('Commerce role required',frappe.PermissionError)


def validate_draft(values,event):
    allowed={'customer','company','currency','conversion_rate','transaction_date','delivery_date',
             'selling_price_list','items','taxes','ignore_pricing_rule','remarks','docstatus'}
    if set(values)-allowed or values.get('docstatus')!=0:raise ValueError('Only reviewed draft fields accepted')
    if values['currency']!=event['currency']:raise ValueError('Currency mismatch')
    expected={r['erp_item_code']:0 for r in event['lines']}
    for line in event['lines']:expected[line['erp_item_code']]+=int(line['quantity'])
    actual={}
    for row in values['items']:
        if set(row)-{'item_code','qty','rate','delivery_date'}:raise ValueError('Unsupported order line')
        qty=Decimal(str(row['qty']));rate=Decimal(str(row['rate']))
        if not qty.is_finite() or not rate.is_finite() or qty<=0 or rate<0:raise ValueError('Invalid quantity/rate')
        actual[row['item_code']]=actual.get(row['item_code'],0)+qty
    if actual!=expected:raise ValueError('Operational/commercial line mismatch')
    for row in values.get('taxes',[]):
        if set(row)-{'charge_type','account_head','description','tax_amount'} or row['charge_type']!='Actual':
            raise ValueError('Explicit actual tax/shipping accounts required')
    net=sum(Decimal(str(x['qty']))*Decimal(str(x['rate'])) for x in values['items'])
    net+=sum(Decimal(str(x['tax_amount'])) for x in values.get('taxes',[]))
    if not net.is_finite() or net!=Decimal(event['total']):raise ValueError('Reviewed order total mismatch')


@frappe.whitelist(methods=['POST'])
def stage_order(payload):
    _authorized();data=frappe.parse_json(payload);event=data['event'];values=deepcopy(data['reviewed_draft'])
    validate_draft(values,event)
    key=mapping_key(event['provider'],event['site_key'],event['external_order_id'])
    fingerprint=hashlib.sha256(json.dumps(values,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if frappe.db.exists('Commerce Order State',key):
        # Lock state before checking revision and writing ERP status/identities.
        frappe.db.sql('SELECT name FROM `tabCommerce Order State` WHERE name=%s FOR UPDATE',(key,))
        state=frappe.get_doc('Commerce Order State',key);state.check_permission('write')
        if state.draft_hash!=fingerprint:raise ValueError('Commercial drift requires review')
        if int(event['revision'])<state.revision:return {'status':'stale','sales_order':state.sales_order}
        if int(event['revision'])==state.revision and state.status!=event['status']:
            raise ValueError('Same-revision status conflict')
        order=frappe.get_doc('Sales Order',state.sales_order);order.check_permission('read')
        if order.docstatus!=0:raise ValueError('Submitted/cancelled order requires explicit reconciliation')
        state.revision=int(event['revision']);state.status=event['status'];state.save()
    else:
        customer=frappe.get_doc('Customer',values['customer']);customer.check_permission('read')
        for row in values['items']:
            item=frappe.get_doc('Item',row['item_code']);item.check_permission('read')
            if item.disabled or item.has_variants:raise ValueError('Enabled leaf Item required')
        # Reserve the unique source key before creating the ERP document.
        state=frappe.get_doc({'doctype':'Commerce Order State','source_key':key,'provider':event['provider'],
            'site_key':event['site_key'],'external_order_id':event['external_order_id'],'revision':int(event['revision']),
            'status':event['status'],'draft_hash':fingerprint}).insert()
        if event['status'] in ('cancelled','failed','refunded'):
            raise ValueError('Unseen terminal order requires review, not new demand')
        order=frappe.get_doc(dict(values,doctype='Sales Order')).insert()
        if Decimal(str(order.grand_total))!=Decimal(event['total']):raise ValueError('ERP calculated total mismatch')
        state.sales_order=order.name;state.save()
    return {'status':'staged','source_key':key,'sales_order':state.sales_order,
            'sales_invoice':state.sales_invoice,'payment_entry':state.payment_entry,
            'accounting_posted':False,'physical_fulfillment':False}


@frappe.whitelist(methods=['POST'])
def attach_financial_documents(payload):
    """Accounts Manager links already submitted ERP documents; creates none."""
    _authorized(financial=True);data=frappe.parse_json(payload)
    key=mapping_key(data['provider'],data['site_key'],data['external_order_id'])
    frappe.db.sql('SELECT name FROM `tabCommerce Order State` WHERE name=%s FOR UPDATE',(key,))
    state=frappe.get_doc('Commerce Order State',key);state.check_permission('write')
    order=frappe.get_doc('Sales Order',state.sales_order);order.check_permission('read')
    invoice=frappe.get_doc('Sales Invoice',data['sales_invoice']);invoice.check_permission('read')
    payment=frappe.get_doc('Payment Entry',data['payment_entry']);payment.check_permission('read')
    if invoice.docstatus!=1 or invoice.is_return or payment.docstatus!=1 or payment.payment_type!='Receive':
        raise ValueError('Submitted non-return invoice and receipt required')
    if Decimal(str(invoice.grand_total))!=Decimal(str(order.grand_total)):
        raise ValueError('Partial invoice needs separate explicit reconciliation')
    if invoice.customer!=order.customer or invoice.company!=order.company or invoice.currency!=order.currency:
        raise ValueError('Invoice party/company/currency mismatch')
    if not invoice.items or any(r.sales_order!=order.name for r in invoice.items):raise ValueError('Invoice does not exclusively reference this order')
    if payment.party_type!='Customer' or payment.party!=order.customer or payment.company!=order.company:
        raise ValueError('Payment party/company mismatch')
    if payment.paid_from_account_currency!=invoice.currency:raise ValueError('Payment currency mismatch')
    refs=[r for r in payment.references if r.reference_doctype=='Sales Invoice' and r.reference_name==invoice.name]
    if len(payment.references)!=1 or len(refs)!=1 or Decimal(str(refs[0].allocated_amount))!=Decimal(str(invoice.grand_total)):
        raise ValueError('Exact invoice allocation required; partial/multi-currency review is separate')
    if payment.paid_to_account_currency!=invoice.currency or Decimal(str(payment.received_amount))!=Decimal(str(invoice.grand_total)):
        raise ValueError('Net/foreign-currency receipts require separate settlement reconciliation')
    if state.sales_invoice and state.sales_invoice!=invoice.name or state.payment_entry and state.payment_entry!=payment.name:
        raise ValueError('Financial identity already linked')
    for field,value in [('sales_invoice',invoice.name),('payment_entry',payment.name)]:
        kind={'sales_invoice':'Sales Invoice','payment_entry':'Payment Entry'}[field]
        reference_key=hashlib.sha256(json.dumps([kind,value]).encode()).hexdigest()
        if frappe.db.exists('Commerce Financial Link',reference_key):
            link=frappe.get_doc('Commerce Financial Link',reference_key);link.check_permission('read')
            if link.source_order!=key:raise ValueError('Financial document belongs to another source order')
        else:
            frappe.get_doc({'doctype':'Commerce Financial Link','reference_key':reference_key,
                'source_order':key,'reference_doctype':kind,'reference_name':value}).insert()
    state.sales_invoice=invoice.name;state.payment_entry=payment.name;state.save()
    return {'source_key':key,'sales_order':order.name,'sales_invoice':invoice.name,'payment_entry':payment.name,'created':False}
