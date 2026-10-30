"""Permission-aware, transaction-scoped historical Customer/draft SO import."""
import hashlib
import json
from decimal import Decimal
import frappe


def _ensure(key, payload, kind, values):
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    if frappe.db.exists('Commerce Migration Identity', key):
        old = frappe.get_doc('Commerce Migration Identity', key)
        old.check_permission('read')
        if old.payload_hash != fingerprint or old.target_doctype != kind:
            raise ValueError('Historical source or review drift requires reconciliation')
        target = frappe.get_doc(kind, old.target_name)
        target.check_permission('read')
        if kind == 'Sales Order' and target.docstatus != 0:
            raise ValueError('Historical order was submitted/cancelled; manual reconciliation required')
        return target
    # A concurrent insert loses on the unique identity key and its entire POST
    # rolls back, including the created document. Retry then resolves the winner.
    doc = frappe.get_doc(dict(values, doctype=kind)).insert()
    frappe.get_doc({'doctype': 'Commerce Migration Identity', 'source_key': key,
                    'payload_hash': fingerprint, 'source_payload': json.dumps(payload, sort_keys=True),
                    'target_doctype': kind, 'target_name': doc.name}).insert()
    return doc


@frappe.whitelist(methods=['POST'])
def import_history(payload):
    if not frappe.conf.get('commerce_history_import_enabled'):
        raise ValueError('History imports require explicit site configuration')
    if not {'System Manager', 'Sales Manager'} & set(frappe.get_roles()):
        frappe.throw('Sales Manager required', frappe.PermissionError)
    plan = frappe.parse_json(payload)
    if plan.get('financial_replay') is not False or plan.get('fulfillment_replay') is not False:
        raise ValueError('Historical replay prohibited')
    customers, orders = {}, []
    for row in plan['customers']:
        allowed = {'customer_name', 'customer_type', 'customer_group', 'territory'}
        if set(row['customer']) - allowed:
            raise ValueError('Unsupported Customer fields')
        customer=_ensure(row['source_key'],row,'Customer',row['customer'])
        customers[row['source_key']]=customer.name
        links=[{'link_doctype':'Customer','link_name':customer.name}]
        if row.get('contact'):
            contact=dict(row['contact'])
            if set(contact)-{'first_name','last_name','email_ids','phone_nos'}:raise ValueError('Unsupported Contact fields')
            for email in contact.get('email_ids',[]):
                if set(email)-{'email_id','is_primary'}:raise ValueError('Unsupported Contact email fields')
            for phone in contact.get('phone_nos',[]):
                if set(phone)-{'phone','is_primary_phone','is_primary_mobile_no'}:raise ValueError('Unsupported Contact phone fields')
            contact['links']=links
            _ensure(row['source_key']+':contact',row['contact'],'Contact',contact)
        for row_address in row.get('addresses',[]):
            address=dict(row_address);source_id=address.pop('source_address_id')
            allowed_address={'address_title','address_type','address_line1','address_line2','city','state','pincode','country','email_id','phone'}
            if set(address)-allowed_address:raise ValueError('Unsupported Address fields')
            address['links']=links
            key=hashlib.sha256((row['source_key']+':address:'+str(source_id)).encode()).hexdigest()
            _ensure(key,row_address,'Address',address)
    for row in plan['orders']:
        values = dict(row['sales_order'])
        allowed = {'company', 'currency', 'conversion_rate', 'transaction_date', 'delivery_date',
                   'selling_price_list', 'items', 'taxes', 'ignore_pricing_rule', 'docstatus', 'remarks'}
        if set(values) - allowed or values.get('docstatus') != 0:
            raise ValueError('Only draft historical Sales Orders allowed')
        for line in values['items']:
            if set(line) - {'item_code', 'qty', 'rate', 'delivery_date'}:
                raise ValueError('Unsupported order line fields')
            item = frappe.get_doc('Item', line['item_code']); item.check_permission('read')
            if item.has_variants or item.disabled:
                raise ValueError('Historical orders require enabled leaf Items')
        for tax in values.get('taxes', []):
            if set(tax) - {'charge_type', 'account_head', 'description', 'tax_amount'} or tax['charge_type'] != 'Actual':
                raise ValueError('Only explicitly reviewed actual charges allowed')
        values['customer'] = customers[row['customer_key']]
        order = _ensure(row['source_key'], row, 'Sales Order', values)
        if Decimal(str(order.grand_total)) != Decimal(row['expected_total']):
            raise ValueError('ERP rounded/converted total differs from source; reconcile before retry')
        orders.append(order.name)
    # Frappe POST commits only after successful return. Never commit partial work.
    return {'customers': customers, 'draft_sales_orders': orders,
            'invoices_created': 0, 'payments_created': 0, 'fulfillment_triggered': False}
