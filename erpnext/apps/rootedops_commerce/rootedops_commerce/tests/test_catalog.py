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

    def test_native_item_price_import_catalog_retry_and_drift(self):
        from rootedops_commerce.api import import_product
        price_list = '_Test Commerce Native USD'
        if not frappe.db.exists('Price List', price_list):
            frappe.get_doc({'doctype':'Price List','price_list_name':price_list,
                            'currency':'USD','selling':1,'enabled':1}).insert()
        code = '_Test Commerce Native Price'
        payload = {
            'item': {'item_code':code,'item_name':'Native price fixture',
                     'item_group':'_Test Commerce Group','stock_uom':'Nos'},
            'content': {'item':code,'public_title':'Native price fixture',
                        'source_key':'synthetic:native-price','source_payload':'{"fixture":"native-price"}'},
            'mapping': {'item':code,'provider':'woocommerce','site_key':'synthetic',
                        'external_product_id':'native-price','external_sku':code},
            'price': {'price_list':price_list,'currency':'USD','item_price_rate':'12.50'}}
        first = import_product(payload)
        self.assertEqual(first, import_product(payload))
        filters = {'item_code':code,'price_list':price_list,'currency':'USD','uom':'Nos'}
        self.assertEqual(frappe.db.count('Item Price', filters), 1)
        self.assertEqual(float(frappe.db.get_value('Item Price',filters,'price_list_rate')), 12.5)
        response = catalog(code, price_list)
        self.assertEqual(len(response['prices']), 1)
        self.assertEqual(float(response['prices'][0]['item_price_rate']), 12.5)
        self.assertNotIn('price_list_rate', response['prices'][0])
        payload['price']['item_price_rate'] = '13.00'
        with self.assertRaises(frappe.ValidationError):
            import_product(payload)
        self.assertEqual(float(frappe.db.get_value('Item Price',filters,'price_list_rate')), 12.5)
        self.assertEqual(frappe.db.get_value('Item', code, 'is_stock_item'), 0)

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

    def test_native_order_staging_replay_and_cancel_never_post_accounting(self):
        from rootedops_commerce.order_service import stage_order
        from frappe.utils import today
        if not frappe.db.exists('Warehouse Type','Transit'):
            values={'doctype':'Warehouse Type','name':'Transit'}
            autoname=frappe.get_meta('Warehouse Type').autoname or ''
            if autoname.startswith('field:'):values[autoname.split(':',1)[1]]='Transit'
            frappe.get_doc(values).insert()
        company='_Test Commerce Company'
        if not frappe.db.exists('Company',company):
            frappe.get_doc({'doctype':'Company','company_name':company,'abbr':'TCC',
                'default_currency':'USD','country':'United States','chart_of_accounts':'Standard'}).insert()
        if not frappe.db.exists('Price List','_Test Commerce USD'):
            frappe.get_doc({'doctype':'Price List','price_list_name':'_Test Commerce USD','currency':'USD','selling':1,'enabled':1}).insert()
        customer=frappe.get_doc({'doctype':'Customer','customer_name':'Synthetic order customer','customer_type':'Individual'}).insert()
        item=frappe.get_doc({'doctype':'Item','item_code':'_Test Commerce Order','item_name':'Synthetic order item',
                            'item_group':'_Test Commerce Group','stock_uom':'Nos','is_stock_item':0}).insert()
        event={'schema_version':1,'provider':'woocommerce','site_key':'native','external_order_id':'order-native',
               'revision':1,'status':'processing','currency':'USD','total':'10.00',
               'lines':[{'erp_item_code':item.name,'quantity':1}]}
        draft={'customer':customer.name,'company':company,'currency':'USD','conversion_rate':1,
               'transaction_date':today(),'delivery_date':today(),'selling_price_list':'_Test Commerce USD',
               'items':[{'item_code':item.name,'qty':1,'rate':'10.00','delivery_date':today()}],
               'taxes':[],'docstatus':0,'ignore_pricing_rule':1}
        before_invoice=frappe.db.count('Sales Invoice');before_payment=frappe.db.count('Payment Entry')
        old=frappe.conf.get('commerce_order_integration_enabled');frappe.conf.commerce_order_integration_enabled=True
        try:
            first=stage_order({'event':event,'reviewed_draft':draft})
            second=stage_order({'event':event,'reviewed_draft':draft})
            self.assertEqual(first['sales_order'],second['sales_order'])
            event.update(revision=2,status='cancelled')
            result=stage_order({'event':event,'reviewed_draft':draft})
            self.assertEqual(result['sales_order'],first['sales_order'])
            self.assertEqual(frappe.db.get_value('Sales Order',first['sales_order'],'docstatus'),0)
            with self.assertRaisesRegex(frappe.ValidationError,'Commerce order requires'):
                frappe.get_doc('Sales Order',first['sales_order']).submit()
            self.assertEqual(frappe.db.count('Sales Invoice'),before_invoice)
            self.assertEqual(frappe.db.count('Payment Entry'),before_payment)
            # An explicitly submitted operational order can still resolve links.
            # Updating source state never cancels or posts its ERP documents.
            event.update(revision=3,status='processing')
            stage_order({'event':event,'reviewed_draft':draft})
            order=frappe.get_doc('Sales Order',first['sales_order']);order.submit()
            from rootedops_commerce.order_service import resolve_order
            self.assertEqual(resolve_order(event)['sales_order'],order.name)
            event.update(revision=4,status='cancelled')
            result=stage_order({'event':event,'reviewed_draft':draft})
            self.assertTrue(result['reconciliation_required'])
            self.assertEqual(frappe.db.get_value('Sales Order',order.name,'docstatus'),1)
            self.assertEqual(frappe.db.count('Sales Invoice'),before_invoice)
            self.assertEqual(frappe.db.count('Payment Entry'),before_payment)
            if frappe.local.site == 'erp-test.danks.store':
                from rootedops_commerce.customer_sync import link_key
                shop = 'shop-test.danks.store'
                registered = frappe.get_doc(dict(doctype='Customer',
                    customer_name='Synthetic linked Woo buyer', customer_type='Individual')).insert()
                frappe.get_doc(dict(doctype='Commerce Customer Link', source_key=link_key(shop, '123'),
                                    site_key=shop, woo_customer_id='123', customer=registered.name)).insert()
                event.update(site_key=shop, revision=10, status='pending',
                             order_intake_mode='unpaid_pilot', payment_processor='manual_unpaid',
                             lines=[{'line_id': '1', 'erp_item_code': item.name, 'quantity': 1}],
                             line_amounts={'1': '10.00'})
                for woo_customer_id, order_id, expected in (
                    (None, '451', customer.name), ('123', '452', registered.name),
                ):
                    reviewed = dict(draft)
                    if woo_customer_id is not None:
                        del reviewed['customer']
                    event.update(external_customer_id=woo_customer_id, external_order_id=order_id)
                    result = stage_order({'event': event, 'reviewed_draft': reviewed})
                    draft_order = frappe.get_doc('Sales Order', result['sales_order'])
                    self.assertEqual(draft_order.customer, expected)
                    self.assertEqual(draft_order.docstatus, 0)
                    self.assertFalse(result['accounting_posted'])

                self._assert_native_capture_recovery(company, event, draft)
        finally:frappe.conf.commerce_order_integration_enabled=old

    def _assert_native_capture_recovery(self, company, event, draft):
        import hmac
        from unittest.mock import patch

        from rootedops_commerce.clover_payment import reconcile_capture
        from rootedops_commerce.external_receipt import canonical
        from rootedops_commerce.order_service import stage_order

        year = draft['transaction_date'][:4]
        if not frappe.db.exists('Fiscal Year', {'year_start_date': year + '-01-01',
                                               'year_end_date': year + '-12-31'}):
            frappe.get_doc(dict(doctype='Fiscal Year', year='Commerce ' + year,
                                year_start_date=year + '-01-01', year_end_date=year + '-12-31')).insert()
        parent = frappe.db.get_value('Account', {'company': company, 'root_type': 'Asset', 'is_group': 1})
        account_name = 'Fixture Clover Clearing'
        clearing = frappe.get_doc(dict(doctype='Account', account_name=account_name, parent_account=parent,
                                      company=company, account_type='Bank', account_currency='USD')).insert()
        secret = 'synthetic-capture-proof-fixture-only'
        with patch.dict(frappe.conf, {'commerce_clover_capture_pilot': dict(enabled=True,
                evidence_hmac=secret, merchant_id='SYNTHETIC', company=company,
                clearing_account=clearing.name), 'commerce_mapped_zero_tax_fixture': True}):
            paid = dict(event, order_intake_mode='reviewed_mapping', payment_processor='clover',
                        processor_payment_id='fixture-charge-453', external_order_id='453',
                        external_customer_id=None, status='processing', refunds=[],
                        commercial=dict(line_totals={'1': '10.00'}, shipping='0', tax='0'))
            paid['lines'] = [dict(paid['lines'][0], quantity=2)]
            reviewed = dict(draft, items=[dict(draft['items'][0], qty=2, rate='5.00')])
            order_id = stage_order({'event': paid, 'reviewed_draft': reviewed})['sales_order']
            frappe.get_doc('Sales Order', order_id).submit()
            evidence = dict(provider='woocommerce', site_key=paid['site_key'], external_order_id='453',
                            processor='clover', provider_environment='sandbox',
                            verification='verified_adapter', state='captured', merchant_id='SYNTHETIC',
                            processor_reference_type='clover_ecommerce_charge',
                            payment_id='fixture-charge-453', currency='USD', captured_amount='10.00',
                            refunded_amount='0.00', posting_date=draft['transaction_date'])
            proof = hmac.digest(secret.encode(), canonical(evidence), 'sha256').hex()
            count = frappe.db.count('Sales Invoice')
            frappe.db.savepoint('capture_fixture')
            path = 'erpnext.accounts.doctype.payment_entry.payment_entry.get_payment_entry'
            with patch(path, side_effect=RuntimeError('Fixture payment failure')):
                with self.assertRaisesRegex(RuntimeError, 'Fixture payment failure'):
                    reconcile_capture(evidence, proof)
            frappe.db.rollback(save_point='capture_fixture')
            self.assertEqual(frappe.db.count('Sales Invoice'), count)
            first = reconcile_capture(evidence, proof)
            self.assertEqual(first, reconcile_capture(evidence, proof))
            invoice = frappe.get_doc('Sales Invoice', first['sales_invoice'])
            payment = frappe.get_doc('Payment Entry', first['payment_entry'])
            self.assertEqual((invoice.docstatus, invoice.update_stock, payment.docstatus), (1, 0, 1))
            self.assertEqual(payment.paid_to, clearing.name)

            from rootedops_commerce.fulfillment import acknowledge_shipment
            shipment_key = 'synthetic-shipment-proof-fixture-only'
            with patch.dict(frappe.conf, {'commerce_mp_fulfillment_pilot':
                                         dict(enabled=True, movement_hmac=shipment_key)}):
                shipment = dict(provider='woocommerce', site_key=paid['site_key'],
                                external_order_id='453', reference='fixture-movement',
                                sales_order=order_id,
                                lines=[dict(line_id='1', item_code=reviewed['items'][0]['item_code'],
                                            quantity=1)])
                proof = hmac.digest(shipment_key.encode(), canonical(shipment), 'sha256').hex()
                deliveries = frappe.db.count('Delivery Note')
                projected = acknowledge_shipment(shipment, proof)
                self.assertEqual(projected['status'], 'partial')
                cancelled = dict(paid, revision=paid['revision'] + 1, status='cancelled')
                stage_order({'event': cancelled, 'reviewed_draft': reviewed})
                self.assertEqual(projected, acknowledge_shipment(shipment, proof))
                self.assertEqual(frappe.db.count('Delivery Note'), deliveries)
