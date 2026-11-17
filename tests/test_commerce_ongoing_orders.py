from datetime import datetime
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch

from test_commerce_order_pilot import ROOT
from production_order import admit_order, order_scope

spec = importlib.util.spec_from_file_location('live_approve_fixture', ROOT / 'scripts/commerce_live_approve.py')
approve = importlib.util.module_from_spec(spec)
spec.loader.exec_module(approve)


class OngoingOrders(unittest.TestCase):
    def setUp(self):
        self.pilot = dict(enabled=True, woo_order_id=10, not_before_gmt='2026-11-17T00:00:00',
                          capture_enabled=True, clover_charge_id='capture-original')

    def test_review_intake_admits_two_orders_without_default_worker_selection(self):
        review = approve.apply(self.pilot, 'review')
        selected, cutoff = order_scope(review, 'serve')
        self.assertIsNone(selected)
        for order_id in (11, 12):
            self.assertTrue(admit_order(dict(id=order_id, date_created_gmt='2026-11-17T00:00:01'), selected, cutoff))
        self.assertFalse(admit_order(dict(id=11, date_created_gmt='2026-11-16T23:00:00'), selected, cutoff))
        self.assertFalse(admit_order(dict(id=11, date_created_gmt='2026-11-17T00:00:01',
                                          status='checkout-draft'), selected, cutoff))
        with self.assertRaisesRegex(ValueError, 'Select a single'):
            order_scope(review, 'work-once')
        self.assertEqual(order_scope(review, 'work-once', '11')[0], '11')
        with self.assertRaisesRegex(ValueError, 'pilot mode'):
            order_scope(self.pilot, 'work-once', '11')

    def test_erp_separate_approval_preserves_pilot_and_binds_capture(self):
        review = approve.apply(self.pilot, 'review')
        review = approve.apply(review, 'admit', '11')
        review = approve.apply(review, 'capture', '11', 'capture-new')
        false = SimpleNamespace(local=SimpleNamespace(site='erp.danks.store'),
                                conf={'commerce_live_order': review})
        path = ROOT / 'erpnext/apps/rootedops_commerce/rootedops_commerce/live_order.py'
        spec = importlib.util.spec_from_file_location('erp_live_order_fixture', path)
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'frappe': false}):
            spec.loader.exec_module(module)
        base = dict(provider='woocommerce', site_key='danks.store')
        self.assertTrue(module.authorize(dict(base, external_order_id='10', payment_id='capture-original'), capture=True))
        self.assertTrue(module.authorize(dict(base, external_order_id='11', payment_id='capture-new'), capture=True))
        with self.assertRaisesRegex(ValueError, 'individual ERP approval'):
            module.authorize(dict(base, external_order_id='12'))
        with self.assertRaisesRegex(ValueError, 'outside the approved'):
            module.authorize(dict(base, external_order_id='11', payment_id='capture-original'), capture=True)
        with self.assertRaisesRegex(ValueError, 'already exists'):
            approve.apply(review, 'capture', '11', 'capture-different')

    def test_rejected_erp_preflight_does_not_freeze_quote_or_reserve(self):
        from unittest.mock import Mock
        from inbox import deliver_one

        inbox, mp, erp = Mock(), Mock(), Mock(production=True)
        erp.validate_production.side_effect = RuntimeError('production quote mismatch')
        inbox.claim.return_value = {'payload': {'site_key': 'danks.store',
            'order_intake_mode': 'unpaid_pilot_pending', 'event_id': 'fixture'},
            'mp_receipt': None, 'raw_pending': b'{}'}
        with patch('inbox.woo_source', return_value=({}, {})), patch('inbox.normalize_order',
                return_value={'order_intake_mode': 'reviewed_mapping'}):
            erp.mapped_draft.return_value = ({}, {})
            self.assertTrue(deliver_one(inbox, mp, erp, site='danks.store', order_id='11',
                                      pilot_configs={'danks.store': {}}))
        inbox.materialize_order.assert_not_called()
        mp.assert_not_called()
        inbox.fail.assert_called_once()
