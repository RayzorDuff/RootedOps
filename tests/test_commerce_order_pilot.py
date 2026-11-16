"""Synthetic Woo REST order contracts and the unpaid ERP pilot boundary."""
import base64
import hmac
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'integrations/commerce'))
sys.path.insert(0, str(ROOT / 'erpnext/apps/rootedops_commerce'))

from orders import OrderReview, normalize_order, woo_source

SECRET = 'synthetic-unpaid-pilot-webhook-fixture'
SITE = 'shop-test.danks.store'


def sign(raw):
    return base64.b64encode(hmac.digest(SECRET.encode(), raw, 'sha256')).decode()


def fixture():
    return dict(id=10, customer_id=0, status='pending', currency='USD', total='12.00',
                date_modified_gmt='2026-11-15T21:00:00', date_paid_gmt=None,
                payment_method='', transaction_id='', discount_total='0.00',
                discount_tax='0.00', shipping_total='0.00', shipping_tax='0.00',
                cart_tax='0.00', total_tax='0.00', shipping_lines=[], fee_lines=[],
                tax_lines=[], coupon_lines=[], refunds=[],
                billing={'email': 'synthetic@example.invalid', 'address_1': '1 Synthetic Street'},
                shipping={'address_1': '2 Synthetic Street'},
                line_items=[dict(id=1, product_id=1, variation_id=0, sku='NATIVE-WOO-SYN',
                                 quantity=1, subtotal='12.00', total='12.00',
                                 subtotal_tax='0.00', total_tax='0.00')])


class UnpaidOrderPilot(unittest.TestCase):
    def setUp(self):
        self.config = dict(mappings={'1': dict(sku='NATIVE-WOO-SYN', ecommerce_id=4,
                                                 erp_item_code='ERP-SYN-1')},
                           gateways={'': 'manual_unpaid'}, pilot_items={'ERP-SYN-1'})

    def normalize(self, order):
        source, identity = woo_source(json.dumps(order).encode(), SITE, 'fixture-receipt')
        return normalize_order(source, identity, **self.config)

    def test_guest_and_registered_identity_without_contact_data(self):
        for customer_id, expected in ((0, None), (23, '23')):
            event = self.normalize(dict(fixture(), customer_id=customer_id))
            self.assertEqual(event['external_customer_id'], expected)
            self.assertEqual(event['line_amounts'], {'1': '12.00'})
            self.assertEqual(event['line_sources']['1']['product_id'], '1')
            self.assertNotIn('Synthetic Street', json.dumps(event))
            self.assertNotIn('synthetic@example.invalid', json.dumps(event))

    def test_mapping_gates(self):
        for overrides, expected in (({'mappings': {}}, 'item_unmapped'),
                                     ({'mappings': {'1': []}}, 'item_mapping_review'),
                                     ({'pilot_items': {'other'}}, 'item_mapping_review')):
            with self.subTest(expected=expected), patch.dict(self.config, overrides):
                with self.assertRaisesRegex(OrderReview, expected):
                    self.normalize(fixture())
        self.config['mappings']['1']['enabled'] = False
        with self.assertRaisesRegex(OrderReview, 'item_disabled'):
            self.normalize(fixture())

    def test_reject_paid_shipping_discount_and_quote(self):
        for changes, code in (({'status': 'processing'}, 'gateway_review'),
                              ({'date_paid_gmt': '2026-11-15T21:00:00'}, 'gateway_review'),
                              ({'transaction_id': 'capture'}, 'gateway_review'),
                              ({'shipping_total': '5.00'}, 'commercial_review'),
                              ({'discount_total': '1.00'}, 'commercial_review'),
                              ({'total_tax': '0.01'}, 'commercial_review'),
                              ({'total': '13.00'}, 'commercial_review')):
            with self.subTest(changes=changes), self.assertRaisesRegex(OrderReview, code):
                self.normalize(dict(fixture(), **changes))

    def test_erp_rejects_wrong_site_guest_without_review_and_rate_swaps(self):
        fake = SimpleNamespace(whitelist=lambda **_: lambda f: f,
                               local=SimpleNamespace(site='erp.danks.store'))
        path = ROOT / 'erpnext/apps/rootedops_commerce/rootedops_commerce/order_service.py'
        spec = importlib.util.spec_from_file_location('order_service_fixture', path)
        service = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"frappe": fake}):
            spec.loader.exec_module(service)
        event = self.normalize(fixture())
        with self.assertRaisesRegex(ValueError, 'matching staging ERP'):
            service._pilot_customer(event, {'customer': 'SYN-GUEST'})
        fake.local.site = 'erp-test.danks.store'
        with self.assertRaisesRegex(ValueError, 'reviewed guest'):
            service._pilot_customer(event, {})
        service._pilot_customer(event, {'customer': 'SYN-GUEST'})
        service._pilot_customer(self.normalize(dict(fixture(), customer_id=23)), {})
        service._validate_pilot_commercial(dict(items=[dict(item_code='ERP-SYN-1', qty=1, rate='12')]), event)
        with self.assertRaisesRegex(ValueError, 'ERP Item amounts'):
            service._validate_pilot_commercial(dict(items=[dict(item_code='ERP-SYN-1', qty=1, rate='11')]), event)
