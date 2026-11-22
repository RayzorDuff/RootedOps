"""Later receipts and partial financial recovery use stable reviewed order scope."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'integrations/commerce'))
import production_order as runner


class ReviewedCycleTests(unittest.TestCase):
    def config(self, directory):
        return dict(mode='review', enabled=True, automation_enabled=True,
                    not_before_gmt='2026-11-21T00:00:00', quote_directory=directory,
                    draft_policy={}, approved_item_codes=['SYNTHETIC'], mappings={})

    def quote(self, directory, order_id):
        path = Path(directory) / (order_id + '.json')
        path.write_text(json.dumps(dict(source_order=order_id)))
        path.chmod(0o600)

    def test_two_approved_orders_recover_capture_without_changing_the_posting_date(self):
        with tempfile.TemporaryDirectory() as directory:
            for order_id in ['11', '12']:
                self.quote(directory, order_id)
            config = self.config(directory)
            config.update(automatic_capture=True, capture_posting_dates={'11': '2026-11-21', '12': '2026-11-21'})
            inbox = Mock()
            inbox.completed_woo_payment_source.return_value = ({'status': 'processing', 'refunds': []}, 'SYNTHETIC')
            confirmed = set()

            def capture(inbox, mp, erp, clover, key, posting_date, secret, **kwargs):
                if key[2] == '11' and capture_mock.call_count == 1:
                    raise TimeoutError('Lost after ERP financial commit')
                confirmed.add(key[2])
                return {'status': 'confirmed'}

            with patch.dict(os.environ, ERP_AUTHORIZATION='synthetic', CLOVER_LIVE_MERCHANT_ID='synthetic',
                            CLOVER_LIVE_PRIVATE_KEY='synthetic', COMMERCE_CAPTURE_EVIDENCE_KEY='synthetic'), \
                    patch.object(runner, 'ReviewedERP'), patch.object(runner, 'CloverSandboxEvidence'), \
                    patch.object(runner, 'deliver_one', side_effect=[True, True, False, False]) as deliver, \
                    patch.object(runner, 'order_ledger', side_effect=lambda mp, key: {'reservation_confirmed': key[2] in confirmed}), \
                    patch.object(runner, 'reconcile_capture', side_effect=capture) as capture_mock:
                first = runner.cycle(inbox, object(), config)
                self.assertEqual([row['capture'] for row in first], ['capture_review', 'confirmed'])
                second = runner.cycle(inbox, object(), config)
                self.assertEqual(second[0]['capture'], 'confirmed')
                self.assertNotIn('capture', second[1])
                self.assertEqual(capture_mock.call_count, 3)
                self.assertEqual({call.args[5] for call in capture_mock.call_args_list}, {'2026-11-21'})
                self.assertEqual([call.kwargs['order_id'] for call in deliver.call_args_list], ['11', '12', '11', '12'])

    def test_wrong_quote_identity_cannot_admit_another_order(self):
        with tempfile.TemporaryDirectory() as directory:
            self.quote(directory, '11')
            Path(directory, '11.json').write_text('{"source_order":"12"}')
            with patch.object(runner, 'deliver_one') as deliver:
                with self.assertRaisesRegex(ValueError, 'numeric filename'):
                    runner.cycle(Mock(), object(), self.config(directory))
                deliver.assert_not_called()

    def test_financial_automation_is_disabled_until_explicitly_enabled(self):
        with tempfile.TemporaryDirectory() as directory:
            self.quote(directory, '11')
            with patch.dict(os.environ, ERP_AUTHORIZATION='synthetic'), patch.object(runner, 'ReviewedERP'), \
                    patch.object(runner, 'deliver_one', return_value=False), patch.object(runner, 'CloverSandboxEvidence') as clover:
                self.assertEqual(runner.cycle(Mock(), object(), self.config(directory)), [{'order_id': '11', 'worked': False}])
                clover.assert_not_called()
