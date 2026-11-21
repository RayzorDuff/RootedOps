"""Transport changes preserve durable identity and activation boundaries."""
import copy
import importlib.util
from pathlib import Path
import sys
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'integrations/commerce'))
from staging_origin import customer_pair, order_pair
spec = importlib.util.spec_from_file_location('storefront_config', ROOT / 'scripts/commerce_storefront_config.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class HostnameTests(unittest.TestCase):
    def test_transport_change_retains_exact_configuration(self):
        config = {'woo_origin': 'https://shop-test.danks.store', 'site_key': 'danks.store',
                  'customer_sites': {'shop-test.danks.store': {'enabled': True}},
                  'enabled': False, 'approved_orders': {'11': {'enabled': True}},
                  'secret': 'synthetic-only', 'mappings': {'2': 7}}
        before = copy.deepcopy(config)
        changed = module.update(config)
        self.assertEqual(config, before)
        self.assertEqual(changed.pop('woo_origin'), 'https://dankmushrooms.net')
        before.pop('woo_origin')
        self.assertEqual(changed, before)
        with self.assertRaises(ValueError): module.update({'woo_origin': 'https://unknown.invalid'})

    def test_origin_is_separate_from_the_order_identity(self):
        self.assertEqual(customer_pair('https://erp.danks.store', 'https://dankmushrooms.net', True),
                         ('https://erp.danks.store', 'https://dankmushrooms.net'))
        self.assertEqual(order_pair('https://erp.danks.store', 'https://danks.store', production=True),
                         ('https://erp.danks.store', 'https://danks.store'))
        with self.assertRaises(ValueError): order_pair('https://erp.danks.store', 'https://dankmushrooms.net', production=True)
        with self.assertRaises(ValueError): customer_pair('https://erp-test.danks.store', 'https://dankmushrooms.net')
