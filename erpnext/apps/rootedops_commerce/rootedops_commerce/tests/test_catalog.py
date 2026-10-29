"""Run in a disposable Frappe site with bench run-tests --app rootedops_commerce."""
import frappe
from frappe.tests.utils import FrappeTestCase
from rootedops_commerce.api import catalog


class TestCatalog(FrappeTestCase):
    def test_guest_cannot_read_catalog(self):
        item = frappe.get_doc({'doctype':'Item','item_code':'_Test Commerce Permission',
                              'item_name':'Permission test','item_group':'All Item Groups',
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
                              'item_name':'Overrides test','item_group':'All Item Groups',
                              'stock_uom':'Nos','is_stock_item':0}).insert()
        doc=frappe.get_doc({'doctype':'Commercial Product Content','item':item.name,
            'public_title':'Test','channel_overrides':[
                {'provider':'woocommerce','site_key':'test'},
                {'provider':' WooCommerce ','site_key':'test'}]})
        with self.assertRaises(frappe.ValidationError):doc.insert()
