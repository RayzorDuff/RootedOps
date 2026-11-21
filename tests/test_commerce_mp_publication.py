"""Recover one dispatch destination without resending an acknowledged destination."""
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'integrations/commerce'))
from mp_publication import deliver_dispatches


class Result:
    def __init__(self, rows):
        self.rows = rows

    def fetchone(self):
        return self.rows[0]

    def fetchall(self):
        return self.rows


class Database:
    def __init__(self):
        self.pending = {'erp', 'woo'}
        self.updates = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def commit(self):
        pass

    def execute(self, sql, args=()):
        if 'pg_try_advisory_lock' in sql:
            return Result([(True,)])
        if 'SELECT d.provider' in sql:
            return Result([('woocommerce', 'danks.store', '12', 'move-12', target, {})
                           for target in sorted(self.pending)])
        if 'SELECT line_id,count' in sql:
            return Result([('3', 1)])
        if 'SELECT tracking FROM' in sql:
            return Result([({},)])
        if 'UPDATE public.mp_commerce_shipment_delivery' in sql:
            self.updates.append(args)
            if args[0] is None:
                self.pending.remove(args[-1])
        return Result([])


class PublicationTests(unittest.TestCase):
    def test_woo_timeout_reuses_erp_acknowledgment_and_the_same_movement(self):
        db = Database()
        mp = type('MP', (), {'connect': lambda self: db})()
        config = dict(mode='review', woo_origin='https://shop-test.danks.store')
        packets = []

        def request(*args):
            packets.append(args[-1])
            if len(packets) == 1:
                raise TimeoutError('Lost after Woo commit')
            return {'status': 'duplicate'}

        with patch.dict(os.environ, WOO_MP_AUTHORIZATION='synthetic', COMMERCE_SHIPMENT_EVIDENCE_KEY='synthetic'), \
                patch('mp_publication.reconcile_shipment') as erp:
            deliver_dispatches(mp, object(), config, request)
            self.assertEqual(db.pending, {'woo'})
            deliver_dispatches(mp, object(), config, request)
            self.assertEqual(db.pending, set())
            erp.assert_called_once()
        self.assertEqual(packets[0], packets[1])
        self.assertEqual(packets[0]['lines'], [{'line_id': '3', 'quantity': 1}])

    def test_pilot_does_not_deliver_another_orders_dispatch(self):
        db = Database()
        mp = type('MP', (), {'connect': lambda self: db})()
        with patch('mp_publication.reconcile_shipment') as erp:
            self.assertEqual(deliver_dispatches(mp, object(), dict(woo_order_id=99), lambda *a: None), [])
            erp.assert_not_called()
        self.assertEqual(db.updates, [])


if __name__ == '__main__':
    unittest.main()
