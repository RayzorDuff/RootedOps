"""Focused coverage of new real-batch refusal and reconciliation boundaries."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from commerce_catalog_batch import records_for_batch, verify_woo
from catalog_coverage import reconcile
from ecwid_migrate import plan
from reviewed_catalog import compile_catalog


def fixture():
    source = plan({'store_id': '95802503', 'products': [
        {'id': 7, 'sku': '00001', 'name': 'Example', 'enabled': True, 'price': '9.95',
         'options': [], '_combinations': []}]})
    review = {'source_sha256': source['source_sha256'], 'currency': 'USD', 'currency_confirmed': True,
              'selling_price_list': 'Reviewed USD', 'categories': {}, 'attributes': {},
              'items': {'00001': {'item_code': '00001', 'item_group': 'Products', 'stock_uom': 'Nos', 'tax_key': 'reviewed'}},
              'taxes': {'reviewed': {'woocommerce_status': 'taxable', 'woocommerce_class': '', 'reviewed_no_item_tax': True}}}
    return compile_catalog(source, review)


class CatalogBatchTests(unittest.TestCase):
    def test_authentic_rate_namespace_and_non_sellable_projection(self):
        d = fixture(); records = records_for_batch(d)
        self.assertEqual(records[0]['woocommerce']['sku'], '00001')
        self.assertEqual(records[0]['woocommerce']['stock_quantity'], 0)
        self.assertEqual(records[0]['woocommerce']['catalog_visibility'], 'hidden')
        self.assertNotIn('stock_quantity', d['records'][0]['woocommerce'])
        for mutate in (
            lambda r: r['mapping'].update(site_key='other'),
            lambda r: r['woocommerce'].update(regular_price='0.00'),
            lambda r: r['price'].update(item_price_rate='0.00'),
            lambda r: r['woocommerce'].update(status='publish'),
            lambda r: r['content'].update(source_payload=json.dumps({'product': {'id': 7, 'sku': 'different', 'enabled': True, 'price': '9.95'}})),
        ):
            damaged = deepcopy(d); mutate(damaged['records'][0])
            with self.assertRaises(ValueError): records_for_batch(damaged)

    def test_batch_duplicate_and_missing_review_refused(self):
        d = fixture(); d['records'] *= 2
        with self.assertRaises(ValueError): records_for_batch(d)

    def test_missing_variation_evidence_is_not_zero_variations(self):
        for change in ('missing', 'option'):
            d = fixture(); source = json.loads(d['records'][0]['content']['source_payload'])
            if change == 'missing': del source['product']['_combinations']
            else: source['product']['options'] = [{'name': 'Size'}]
            d['records'][0]['content']['source_payload'] = json.dumps(source)
            with self.assertRaisesRegex(ValueError, 'Verified empty'):
                records_for_batch(d)
        d = fixture(); d['review_sha256'] = ''
        with self.assertRaises(ValueError): records_for_batch(d)

    def test_readback_catches_price_content_gallery_and_seo_drift(self):
        record = records_for_batch(fixture())[0]
        actual = deepcopy(record['woocommerce'])
        verify_woo(actual, record)
        for change in ({'regular_price': '10'}, {'description': 'different'},
                       {'images': [{'id': 999}]}, {'meta_data': []}):
            with self.assertRaises(ValueError): verify_woo(dict(actual, **change), record)

    def test_placeholders_preserve_csv_and_never_count_as_migrated(self):
        rows = [dict(product_id='7', sku='00001', name='Example', price='9.95', enabled='no'),
                dict(product_id='8', sku='00002', name='Other', price='9.95', enabled='yes', category1='Disabled')]
        result = reconcile(rows, [{'id': 7, 'enabled': False}])
        self.assertEqual(result['counts'], {'excluded': 1, 'pending': 1})
        self.assertEqual(result['records'][0]['sku'], '00001')
        self.assertIsNone(result['records'][1]['combinations'])
        self.assertEqual(result['candidate_batches'], [])
        with self.assertRaises(ValueError):
            reconcile(rows, verified=[{'ecwid_product_id': '7', 'erp_item': '00001', 'woo_id': 10}])

    def test_source_price_drift_blocks_candidate_but_not_other_records(self):
        rows = [dict(product_id='7', sku='00001', name='Example', price='9.95', enabled='yes', category1='Gourmet Mushrooms'),
                dict(product_id='8', sku='00002', name='Other', price='9.95', enabled='yes', category1='Gourmet Mushrooms')]
        result = reconcile(rows, [{'id': 7, 'sku': '00001', 'price': 10, 'enabled': True, 'options': []}])
        self.assertEqual(result['candidate_batches'], [['8']])
        self.assertFalse(result['records'][0]['combinations_verified'])
        self.assertTrue(result['records'][0]['options_verified'])


if __name__ == '__main__':
    unittest.main()
