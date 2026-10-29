"""Run in a disposable Frappe site with bench run-tests --app rootedops_commerce."""
import frappe
from frappe.tests import IntegrationTestCase
from rootedops_commerce.api import catalog


class TestCatalog(IntegrationTestCase):
    def setUp(self):
        super().setUp()
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
