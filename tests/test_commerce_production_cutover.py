import hmac
import json
from base64 import b64encode
from datetime import datetime
import io
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from test_commerce_order_pilot import ROOT
from inbox import Inbox, application
from production_order import admit_order, reviewed_order
from staging_origin import order_pair
from clover_sandbox import CloverSandboxEvidence


class ProductionCutover(unittest.TestCase):
    def test_scope_is_disabled_by_default_and_rejects_staging_pair(self):
        with self.assertRaises(ValueError):
            reviewed_order({'woo_order_id': 12})
        with self.assertRaises(ValueError):
            order_pair('https://erp.danks.store', 'https://shop-test.danks.store', production=True)
        self.assertEqual(order_pair('https://erp.danks.store', 'https://danks.store', production=True),
                         ('https://erp.danks.store', 'https://danks.store'))

    def test_unsigned_unapproved_and_old_snapshots_never_reach_storage(self):
        inbox = Inbox(None)
        inbox.store = Mock(return_value={'duplicate': False})
        secret = 'synthetic-production-proof-key-only'
        scope = lambda order: admit_order(order, '12', datetime(2026, 11, 17))
        app = application(inbox, {'danks.store': dict(unpaid_pilot=True, secrets=[secret], admit=scope)})

        def receive(order_id, created, signed=True):
            raw = json.dumps(dict(id=order_id, date_created_gmt=created,
                                  date_modified_gmt='2026-11-18T00:00:00')).encode()
            signature = b64encode(hmac.digest(secret.encode(), raw, 'sha256')).decode() if signed else ''
            env = {'REQUEST_METHOD': 'POST', 'SERVER_NAME': 'localhost',
                   'PATH_INFO': '/webhooks/woocommerce/danks.store',
                   'wsgi.input': io.BytesIO(raw), 'CONTENT_LENGTH': str(len(raw)),
                   'CONTENT_TYPE': 'application/json', 'HTTP_X_WC_WEBHOOK_SIGNATURE': signature}
            statuses = []
            result = b''.join(app(env, lambda status, _: statuses.append(status)))
            return statuses[0], json.loads(result)

        now = '2026-11-17T01:00:00'
        self.assertEqual(receive(12, now, False)[0], '400 Bad Request')
        self.assertEqual(receive(13, now)[1], {'ignored': True})
        self.assertEqual(receive(12, '2026-11-16T20:00:00')[1], {'ignored': True})
        inbox.store.assert_not_called()
        self.assertEqual(receive(12, now)[1], {'duplicate': False})
        inbox.store.assert_called_once()

    def test_clover_production_rejects_sandbox_response(self):
        order = dict(site_key='danks.store', external_order_id='12', payment_processor='clover',
                     processor_payment_id='SYNTHETIC-12', currency='USD', total='12', refunds=[])
        charge = dict(object='charge', id='SYNTHETIC-12', livemode=False, external_reference_id='12',
                      status='succeeded', paid=True, captured=True, currency='usd', merchant_id='FIXTURE',
                      amount=1200, amount_captured=1200, amount_refunded=0)
        adapter = CloverSandboxEvidence(site_key='danks.store', merchant_id='FIXTURE', private_key='x' * 32,
                                       enabled=True, production=True, transport=lambda *_: charge)
        with self.assertRaisesRegex(ValueError, 'environment'):
            adapter.evidence(order, reviewed_order=dict(id=12, number='12'))
        charge['livemode'] = True
        result = adapter.evidence(order, reviewed_order=dict(id=12, number='12'))
        self.assertEqual(result['provider_environment'], 'production')
