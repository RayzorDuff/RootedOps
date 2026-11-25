"""Native ERP history adapter, invoked by the operator runner, never an HTTP route."""
import hashlib
import json
import sys
from decimal import Decimal
import frappe

value = json.load(sys.stdin)
frappe.init(site='erp.danks.store', sites_path='.')
frappe.connect()
frappe.set_user('Administrator')
frappe.flags.mute_emails = True
COMPANY = 'Dank Mushrooms, LLC'

try:
    if value['action'] == 'snapshot':
        frappe.db.rollback()
        frappe.db.sql('START TRANSACTION READ ONLY')
        emails = {}
        for row in frappe.get_all('Customer', fields=['name', 'email_id', 'disabled']):
            if row.email_id and not row.disabled:
                emails.setdefault(row.email_id.strip().lower(), set()).add(row.name)
        for row in frappe.get_all('Contact Email', fields=['parent', 'email_id']):
            if not row.email_id:
                continue
            for link in frappe.get_doc('Contact', row.parent).links:
                if link.link_doctype == 'Customer' and frappe.db.exists('Customer', link.link_name):
                    if not frappe.db.get_value('Customer', link.link_name, 'disabled'):
                        emails.setdefault(row.email_id.strip().lower(), set()).add(link.link_name)
        linked, reverse = {}, {}
        for row in frappe.get_all('Commerce Customer Link', filters={'site_key': 'shop-test.danks.store'},
                                  fields=['woo_customer_id', 'customer']):
            if row.customer:
                linked[str(row.woo_customer_id)] = row.customer
                if row.customer in reverse and reverse[row.customer] != str(row.woo_customer_id):
                    raise ValueError('Multiple Woo identities for one customer need review')
                reverse[row.customer] = str(row.woo_customer_id)
        items = {row.name: not row.disabled and not row.has_variants for row in
                 frappe.get_all('Item', fields=['name', 'disabled', 'has_variants'])}
        print(json.dumps(dict(email_customers={k: sorted(v) for k, v in emails.items()},
                              woo_customers=linked, customer_woo=reverse, items=items)))
    elif value['action'] == 'apply':
        company = frappe.get_doc('Company', COMPANY)
        if company.default_currency != 'USD':
            raise ValueError('Unexpected company currency')
        tax_account = frappe.get_doc('Account', 'Sales Tax Payable - DML')
        if tax_account.company != COMPANY or tax_account.root_type != 'Liability' or tax_account.disabled or tax_account.is_group:
            raise ValueError('Invalid existing sales-tax liability account')
        before = {kind: frappe.db.count(kind) for kind in ('Sales Invoice', 'Payment Entry', 'Stock Ledger Entry', 'Email Queue')}
        results = []
        for plan in value['orders']:
            canonical = json.dumps(plan, sort_keys=True, separators=(',', ':'))
            fingerprint = hashlib.sha256(canonical.encode()).hexdigest()
            key = plan['erp_key']
            if frappe.db.exists('Commerce Migration Identity', key):
                old = frappe.get_doc('Commerce Migration Identity', key)
                if old.payload_hash != fingerprint or old.target_doctype != 'Sales Order':
                    raise ValueError('Existing source identity differs; reconcile before retry')
                order = frappe.get_doc('Sales Order', old.target_name)
                if (order.docstatus != 0 or Decimal(str(order.grand_total)) != Decimal(plan['total'])
                        or order.company != COMPANY or order.customer != plan['erp_customer']):
                    raise ValueError('Existing historical order was altered/submitted')
                results.append(dict(source_id=plan['id'], sales_order=order.name, result='reused'))
                continue
            lines = []
            for line in plan['lines']:
                code = line['erp_item']
                if not frappe.db.exists('Item', code):
                    if not line['create_item'] or not code.startswith('ECWID-HIST-'):
                        raise ValueError('Missing reviewed historical Item')
                    group = 'Dank Commerce Services'
                    if not frappe.db.exists('Item Group', group):
                        raise ValueError('Expected reviewed commerce Item Group')
                    frappe.get_doc(dict(doctype='Item', item_code=code,
                        item_name=line['name'][:140], item_group=group, stock_uom='Nos',
                        is_stock_item=0, is_sales_item=1, is_purchase_item=0,
                        description='Historical Ecwid item; source SKU ' + line['sku'],
                        item_defaults=[dict(company=COMPANY, income_account=company.default_income_account,
                                            selling_cost_center=company.cost_center)])).insert()
                item = frappe.get_doc('Item', code)
                if item.disabled or item.has_variants:
                    raise ValueError('Invalid historical Item')
                lines.append(dict(item_code=code, qty=line['quantity'], rate=line['rate'],
                    description=line['name'] + '\nHistorical Ecwid SKU: ' + line['sku']))
            if Decimal(plan['shipping']):
                shipping = frappe.get_doc('Item', 'DML-WEB-SHIPPING')
                if shipping.disabled or shipping.is_stock_item:
                    raise ValueError('Invalid shipping Item')
                lines.append(dict(item_code=shipping.name, qty=1, rate=plan['shipping']))
            taxes = [dict(charge_type='Actual', account_head=tax_account.name,
                description='Historical Ecwid order tax; original total retained', tax_amount=plan['tax'])] if Decimal(plan['tax']) else []
            order = frappe.get_doc(dict(doctype='Sales Order', company=COMPANY,
                customer=plan['erp_customer'], currency='USD', conversion_rate=1,
                selling_price_list='Standard Selling', plc_conversion_rate=1,
                transaction_date=plan['created'][:10], delivery_date=plan['created'][:10],
                ignore_pricing_rule=1, disable_rounded_total=1, taxes_and_charges='',
                items=lines, taxes=taxes,
                remarks='HISTORICAL ECWID — DO NOT SUBMIT OR FULFILL. ' + plan['source_key']
                    + '\nSource payment: ' + plan['source_payment'] + '; fulfillment: ' + plan['source_fulfillment']
                    + '\nTender: ' + str(plan['payment_method']) + '; Woo history is linked by source identity.')).insert()
            if order.docstatus != 0 or Decimal(str(order.grand_total)) != Decimal(plan['total']):
                raise ValueError('ERP historical draft total differs from source')
            frappe.get_doc(dict(doctype='Commerce Migration Identity', source_key=key,
                payload_hash=fingerprint, source_payload=canonical,
                target_doctype='Sales Order', target_name=order.name)).insert()
            results.append(dict(source_id=plan['id'], sales_order=order.name, result='created'))
        if any(frappe.db.count(kind) != count for kind, count in before.items()):
            raise ValueError('Unexpected invoice, payment, stock or notification creation')
        if value.get('dry_run'):
            frappe.db.rollback()
        else:
            frappe.db.commit()
        print(json.dumps(results))
    else:
        raise ValueError('Unknown history action')
finally:
    frappe.db.rollback()
    frappe.destroy()
