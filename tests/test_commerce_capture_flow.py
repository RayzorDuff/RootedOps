import json
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, Mock

from test_commerce_order_pilot import SITE
from payment_reconciliation import reconcile_capture


class CaptureFlow(unittest.TestCase):
    def setUp(self):
        self.order = {'status': 'processing', 'refunds': []}
        self.inbox = Mock()
        self.inbox.completed_woo_payment_source.return_value = self.order, 'WC-001'
        self.clover = Mock()
        self.clover.evidence.return_value = dict(verification='verified_adapter', payment_id='capture-fixture')
        self.erp = SimpleNamespace(base='https://erp-test.danks.store', authorization='synthetic', request=Mock())
        self.result = dict(sales_order='SO', sales_invoice='SI', payment_entry='PE')
        self.erp.request.return_value = {'message': self.result}
        self.db = MagicMock()
        self.inventory = SimpleNamespace(connect=MagicMock())
        self.inventory.connect.return_value.__enter__.return_value = self.db

    def run_capture(self):
        return reconcile_capture(self.inbox, self.inventory, self.erp, self.clover,
                                 ('woocommerce', SITE, '1'), '2026-11-16', 'x' * 32)

    def test_out_of_order_failure_and_refund_cannot_write(self):
        self.order['status'] = 'pending'
        self.assertEqual(self.run_capture()['status'], 'awaiting_paid_woo_snapshot')
        self.clover.evidence.assert_not_called()
        self.order['status'] = 'processing'
        self.clover.evidence.side_effect = ValueError('Failed charge')
        with self.assertRaises(ValueError):
            self.run_capture()
        self.clover.evidence.side_effect = None
        self.order.update(status='refunded', refunds=[{'amount': '9.00'}])
        self.assertEqual(self.run_capture()['status'], 'refund_review')
        self.erp.request.assert_not_called()
        self.db.execute.assert_not_called()

    def test_recovery_after_erp_commit_and_mp_retry(self):
        self.erp.request.side_effect = [TimeoutError(), {'message': self.result}, {'message': self.result}]
        with self.assertRaises(TimeoutError):
            self.run_capture()
        self.db.execute.assert_not_called()
        self.assertEqual(self.run_capture()['payment_entry'], 'PE')
        self.assertEqual(self.run_capture()['sales_invoice'], 'SI')
        requests = self.erp.request.call_args_list
        self.assertTrue(all(call == requests[0] for call in requests))
        packet = json.loads(requests[0].args[-1]['payload'])
        self.assertEqual(packet['provider'], 'woocommerce')
        self.assertEqual(self.db.execute.call_count, 6)
