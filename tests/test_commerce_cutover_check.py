import importlib.util
import io
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[1] / 'scripts/commerce_cutover_check.py'
spec = importlib.util.spec_from_file_location('commerce_cutover_check', path)
cutover = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cutover)


class CutoverCheck(unittest.TestCase):
    def test_rejects_test_hostname_at_any_hop(self):
        with self.assertRaisesRegex(ValueError, 'Unexpected redirect origin'):
            cutover.walk('https://danks.store/products/test', 'danks.store',
                         lambda _: (302, 'https://shop-test.danks.store/product/test'))
        result = cutover.walk('https://qr.danks.store/r?i=fixture', 'danks.store',
                             lambda url: (302, 'https://danks.store/product/fixture')
                             if '/r?' in url else (200, None))
        self.assertEqual([status for _, status in result], [302, 200])

    def test_published_stock_uses_exact_owner_and_quantity(self):
        sample = 'woo_id,parent_woo_id,mp_id,sku,source_key,pool_key,mp_available\n1,,5,ITEM,ecwid:1,5:none,3\n'
        product = dict(id=1, sku='ITEM', type='simple', status='publish', manage_stock=True,
                       backorders='no', stock_quantity=3,
                       meta_data=[dict(key='_rootedops_source_key', value='ecwid:1')])
        self.assertEqual(cutover.stock('danks.store', io.StringIO(sample), 'synthetic',
                                       lambda *_: product), 0)
        self.assertEqual(cutover.stock('danks.store', io.StringIO(sample), 'synthetic',
                                       lambda *_: dict(product, stock_quantity=4)), 1)
