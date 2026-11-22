"""Provision deterministic records in the disposable shared-stack CI site."""
import os
import frappe


def setup():
    if os.environ.get('COMMERCE_NATIVE_CI') != '1' or frappe.local.site != 'erp-test.danks.store':
        raise ValueError('Disposable native CI only')
    if not frappe.db.exists('Warehouse Type', 'Transit'):
        fields = {'doctype': 'Warehouse Type', 'name': 'Transit'}
        autoname = frappe.get_meta('Warehouse Type').autoname or ''
        if autoname.startswith('field:'):
            fields[autoname.split(':', 1)[1]] = 'Transit'
        frappe.get_doc(fields).insert()
    frappe.get_doc(dict(doctype='Company', company_name='Native Woo Fixture', abbr='NWF',
                        default_currency='USD', country='United States',
                        chart_of_accounts='Standard')).insert()
    frappe.get_doc(dict(doctype='Price List', price_list_name='Native Woo USD',
                        currency='USD', selling=1, enabled=1)).insert()
    frappe.get_doc(dict(doctype='Customer', customer_name='Native Woo Guest',
                        customer_type='Individual')).insert()
    if not frappe.db.exists('Item Group', 'All Item Groups'):
        frappe.get_doc(dict(doctype='Item Group', item_group_name='All Item Groups', is_group=1)).insert()
    frappe.get_doc(dict(doctype='Item Group', item_group_name='Native Fixture Items',
                        parent_item_group='All Item Groups')).insert()
    if not frappe.db.exists('UOM', 'Nos'):
        frappe.get_doc(dict(doctype='UOM', uom_name='Nos', must_be_whole_number=1)).insert()
    frappe.get_doc(dict(doctype='Item', item_code='ERP-SYN-1', item_name='Native Woo Item',
                        item_group='Native Fixture Items', stock_uom='Nos', is_stock_item=0)).insert()
    user = frappe.get_doc('User', 'Administrator')
    user.api_key = 'synthetic-native-woo-key'
    user.api_secret = 'synthetic-native-woo-secret'
    user.save()
