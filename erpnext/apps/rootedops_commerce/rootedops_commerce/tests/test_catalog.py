"""Run in a disposable Frappe site with bench run-tests --app rootedops_commerce."""
import frappe
from frappe.tests import IntegrationTestCase
from rootedops_commerce.api import catalog


class TestCatalog(IntegrationTestCase):
    def setUp(self):
        super().setUp()
        if not frappe.db.exists('Item Group', 'All Item Groups'):
            frappe.get_doc({'doctype':'Item Group','item_group_name':'All Item Groups',
                            'is_group':1}).insert()
        if not frappe.db.exists('Item Group', '_Test Commerce Group'):
            frappe.get_doc({'doctype':'Item Group','item_group_name':'_Test Commerce Group',
                            'parent_item_group':'All Item Groups','is_group':0}).insert()
        if not frappe.db.exists('UOM','Nos'):
            frappe.get_doc({'doctype':'UOM','uom_name':'Nos','must_be_whole_number':1}).insert()

    def test_guest_cannot_read_catalog(self):
        item = frappe.get_doc({'doctype':'Item','item_code':'_Test Commerce Permission',
                              'item_name':'Permission test','item_group':'_Test Commerce Group',
                              'stock_uom':'Nos','is_stock_item':0}).insert()
        frappe.get_doc({'doctype':'Commercial Product Content','item':item.name,
                        'public_title':'Test','publication_status':'Draft'}).insert()
        try:
            frappe.set_user('Guest')
            with self.assertRaises(frappe.PermissionError):
                catalog(item.name)
        finally:
            frappe.set_user('Administrator')

    def test_duplicate_override_rejected(self):
        item = frappe.get_doc({'doctype':'Item','item_code':'_Test Commerce Overrides',
                              'item_name':'Overrides test','item_group':'_Test Commerce Group',
                              'stock_uom':'Nos','is_stock_item':0}).insert()
        doc=frappe.get_doc({'doctype':'Commercial Product Content','item':item.name,
            'public_title':'Test','channel_overrides':[
                {'provider':'woocommerce','site_key':'test'},
                {'provider':' WooCommerce ','site_key':'test'}]})
        with self.assertRaises(frappe.ValidationError):doc.insert()

    def test_repeated_import_does_not_duplicate_or_write_stock(self):
        from rootedops_commerce.api import import_product
        import json
        payload = {
            'item': {'item_code':'_Test Commerce Retry','item_name':'Retry',
                     'item_group':'_Test Commerce Group','stock_uom':'Nos'},
            'content': {'item':'_Test Commerce Retry','public_title':'Retry',
                        'source_key':'ecwid:test:product:retry','source_payload':'{"id":"retry"}'},
            'mapping': {'item':'_Test Commerce Retry','provider':'ecwid','site_key':'test',
                        'external_product_id':'retry','external_sku':'_Test Commerce Retry'}}
        first = import_product(json.dumps(payload))
        second = import_product(json.dumps(payload))
        self.assertEqual(first, second)
        self.assertEqual(frappe.db.count('Commercial Product Content', {'item':'_Test Commerce Retry'}), 1)
        self.assertEqual(frappe.db.get_value('Item','_Test Commerce Retry','is_stock_item'), 0)
        payload['content']['source_payload']='{"id":"changed"}'
        with self.assertRaises(frappe.ValidationError):import_product(json.dumps(payload))

    def test_source_archive_identity_and_payload_are_immutable(self):
        doc = frappe.get_doc({'doctype':'Commerce Source Archive',
            'source_key':'ecwid:test:order:archive','record_type':'order','payload':'{"id":"archive"}'}).insert()
        original_hash = doc.payload_hash
        doc.reload()
        self.assertEqual(doc.payload_hash, original_hash)
        doc.source_key = 'ecwid:test:order:other'
        with self.assertRaises(frappe.ValidationError):doc.save()

    def test_guest_cannot_import(self):
        from rootedops_commerce.api import import_product
        try:
            frappe.set_user('Guest')
            with self.assertRaises(frappe.PermissionError):import_product('{}')
        finally:
            frappe.set_user('Administrator')

    def test_history_contact_address_replay_and_order_feature_guard(self):
        from rootedops_commerce.history import import_history
        from rootedops_commerce.order_service import stage_order
        if not frappe.db.exists('Customer Group','_Test Commerce Customers'):
            frappe.get_doc({'doctype':'Customer Group','customer_group_name':'_Test Commerce Customers','is_group':0}).insert()
        if not frappe.db.exists('Territory','_Test Commerce Territory'):
            frappe.get_doc({'doctype':'Territory','territory_name':'_Test Commerce Territory','is_group':0}).insert()
        if not frappe.db.exists('Address Template',{'is_default':1}):
            frappe.get_doc({'doctype':'Address Template','country':'United States','is_default':1,
                            'template':'{{ address_line1 }} {{ city }}'}).insert()
        plan={'financial_replay':False,'fulfillment_replay':False,'customers':[{
            'source_key':'synthetic-native-customer','source_payload':{'id':'native'},
            'customer':{'customer_name':'Synthetic Commerce Customer','customer_type':'Individual',
                        'customer_group':'_Test Commerce Customers','territory':'_Test Commerce Territory'},
            'contact':{'first_name':'Synthetic','email_ids':[{'email_id':'synthetic@example.invalid','is_primary':1}]},
            'addresses':[{'source_address_id':'billing','address_title':'Synthetic billing','address_type':'Billing',
                          'address_line1':'Synthetic test location','city':'Test city','country':'United States'}]}],'orders':[]}
        old=frappe.conf.get('commerce_history_import_enabled');frappe.conf.commerce_history_import_enabled=True
        try:
            first=import_history(plan);second=import_history(plan)
            self.assertEqual(first,second)
            self.assertEqual(frappe.db.count('Commerce Migration Identity',{'target_doctype':'Contact','source_key':'synthetic-native-customer:contact'}),1)
            contact_name=frappe.db.get_value('Commerce Migration Identity','synthetic-native-customer:contact','target_name')
            contact=frappe.get_doc('Contact',contact_name)
            self.assertEqual(contact.links[0].link_name,first['customers']['synthetic-native-customer'])
            self.assertEqual(first['invoices_created'],0)
        finally:frappe.conf.commerce_history_import_enabled=old
        with self.assertRaises(ValueError):stage_order({})
