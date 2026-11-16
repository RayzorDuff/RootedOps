from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, Mock, patch
import sys

from test_commerce_order_pilot import SITE
from shipment_reconciliation import reconcile_shipment


class FulfillmentProjection(unittest.TestCase):
    def test_retry_after_timeout_uses_same_committed_movement(self):
        db = MagicMock()
        inventory = MagicMock()
        inventory.connect.return_value.__enter__.return_value = db
        db.execute.return_value.fetchall.return_value = [('SO', '3', 'ITEM', 1)]
        erp = SimpleNamespace(base='https://erp-test.danks.store', authorization='test', request=Mock())
        erp.request.side_effect = [TimeoutError(), {'message': {'status': 'partial'}}]
        args = inventory, erp, ('woocommerce', SITE, '10'), 'movement-fixture', 'x' * 32
        with self.assertRaises(TimeoutError):
            reconcile_shipment(*args)
        self.assertEqual(reconcile_shipment(*args), {'status': 'partial'})
        self.assertEqual(erp.request.call_args_list[0], erp.request.call_args_list[1])

    def test_erp_quantity_is_per_line_and_cannot_exceed_plan(self):
        fake = SimpleNamespace(whitelist=lambda **_: lambda f: f)
        with patch.dict(sys.modules, {'frappe': fake}):
            from rootedops_commerce.fulfillment import add_quantities
        plan = {'3': {'item_code': 'ITEM', 'quantity': 2}}
        rows = [{'line_id': '3', 'item_code': 'ITEM', 'quantity': 1}]
        partial = add_quantities(plan, {}, rows)
        self.assertEqual(partial, {'3': 1})
        self.assertEqual(add_quantities(plan, partial, rows), {'3': 2})
        with self.assertRaisesRegex(ValueError, 'exceeds'):
            add_quantities(plan, {'3': 2}, rows)
