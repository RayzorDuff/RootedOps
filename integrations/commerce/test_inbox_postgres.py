"""Native integration tests; invoked only with a disposable commerce_test DSN."""
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import hmac
import json
import os
import subprocess
from threading import Thread
import time
from wsgiref.simple_server import make_server
from pathlib import Path
import unittest
from inbox import Inbox, PostgresInventory, ReviewedERP, application, deliver_one, reconcile_order
from runtime import connect_test

class NativeInboxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.connect=staticmethod(connect_test(os.environ['COMMERCE_INBOX_DSN']))
        with cls.connect() as db:
            if db.execute('SELECT EXISTS(SELECT 1 FROM products) OR EXISTS(SELECT 1 FROM lots) OR EXISTS(SELECT 1 FROM mp_commerce_orders)').fetchone()[0]:
                raise ValueError('Native fixture suite requires an empty disposable database')
            db.execute(Path(__file__).with_name('inbox.sql').read_text())
            db.execute('CREATE TABLE erp_draft_probe(source_key text PRIMARY KEY)')
            cls.item=db.execute("INSERT INTO items(item_id,name,category,active) VALUES('INBOX-SYNTHETIC','Synthetic','grain',true) RETURNING nocopk").fetchone()[0]
            loc=db.execute("INSERT INTO locations(name,active,type) VALUES('Inbox synthetic',true,'Storage') RETURNING nocopk").fetchone()[0]
            cls.storage=loc
            db.execute('INSERT INTO products(item_id,storage_location_id,use_by) VALUES(%s,%s,CURRENT_DATE+1),(%s,%s,CURRENT_DATE+1)',(cls.item,loc,cls.item,loc))
            cls.ecommerce=db.execute("INSERT INTO ecommerce(name,item_id,provider,site_key,external_sku,erp_item_code,sync_enabled,status) VALUES('Inbox synthetic',%s,'woocommerce','synthetic','SYN-1','ERP-SYN-1',true,'Sterilized') RETURNING nocopk",(cls.item,)).fetchone()[0]
    def setUp(self):
        with self.connect() as db:
            for table in ['mp_commerce_shipped_products','mp_commerce_shipments','commerce_delivery','commerce_inbox','erp_draft_probe','mp_commerce_erp_links','mp_commerce_payment_matches','mp_commerce_events','mp_commerce_reservations','mp_commerce_orders']:
                db.execute('DELETE FROM '+table)
            db.execute('UPDATE products SET storage_location_id=%s WHERE item_id=%s',(self.storage,self.item))
            db.execute("UPDATE ecommerce SET external_sku='SYN-1', external_product_id=NULL WHERE nocopk=%s",
                       (self.ecommerce,))
        self.inbox=Inbox(self.connect);self.mp=PostgresInventory(self.connect)
    def receive(self, **changes):
        order={'id':10,'status':'processing','currency':'USD','total':'12.00','date_modified_gmt':'2026-10-30T10:00:00',
            'payment_method':'clover_test','transaction_id':'fixture-capture','line_items':[{'id':1,'product_id':1,'variation_id':0,'sku':'SYN-1','quantity':1}],'refunds':[]}
        order.update(changes)
        raw=json.dumps(order).encode()
        secret='synthetic-native-webhook-fixture-secret'
        signature=base64.b64encode(hmac.digest(secret.encode(),raw,'sha256')).decode()
        return self.inbox.receive(raw,signature,secrets=[secret],site='synthetic',
            mappings={'1':{'sku':'SYN-1','ecommerce_id':self.ecommerce,'erp_item_code':'ERP-SYN-1'}},gateways={'clover_test':'clover'})
    def test_customer_receipt_is_durable_and_excluded_from_order_claims(self):
        from customer_signals import ACTION, PROVIDER
        raw = json.dumps(dict(action=ACTION, arg=dict(id=12, scope='account',
                        event='a23c14be-23ad-4b5a-97c2-fdf7944ed25b', digest='a'*64))).encode()
        secret = 'synthetic-native-customer-webhook-secret'
        signature = base64.b64encode(hmac.digest(secret.encode(), raw, 'sha256')).decode()
        kwargs = dict(secrets=[secret], site='shop-test2.danks.store')
        self.assertFalse(self.inbox.receive_customer(raw, signature, **kwargs)['duplicate'])
        self.assertTrue(self.inbox.receive_customer(raw, signature, **kwargs)['duplicate'])
        self.assertIsNone(self.inbox.claim())
        self.assertIsNone(self.inbox.claim(provider=PROVIDER, site='another-store'))
        claim = self.inbox.claim(provider=PROVIDER, site=kwargs['site'])
        self.assertEqual(claim['payload']['id'], 12)

    def test_concurrent_receipt_and_lost_erp_response(self):
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(lambda _:self.receive(),range(2)))
        self.assertEqual(sorted(r['duplicate'] for r in results),[False,True]);calls=[]
        def erp(event,receipt):
            with self.connect() as db:
                db.execute('INSERT INTO erp_draft_probe VALUES(%s) ON CONFLICT DO NOTHING',(event['external_order_id'],))
            calls.append(1)
            if len(calls)==1:raise TimeoutError('synthetic lost response after commit')
            return {'sales_order':'SYNTHETIC-SO'}
        deliver_one(self.inbox,self.mp,erp,retry_seconds=0)
        deliver_one(self.inbox,self.mp,erp,retry_seconds=0)
        with self.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM mp_commerce_events').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT count(*) FROM erp_draft_probe').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT state FROM commerce_delivery').fetchone()[0],'done')
            self.assertEqual(db.execute('SELECT sum(quantity) FROM mp_commerce_reservations').fetchone()[0],1)
    def test_dead_letter_replay_and_lease_fencing(self):
        received=self.receive();old=self.inbox.claim()
        with self.connect() as db:db.execute("UPDATE commerce_delivery SET lease_until=now()-interval '1 second'")
        new=self.inbox.claim()
        with self.assertRaises(ValueError):self.inbox.record(old,'mp',{'status':'applied'})
        self.inbox.fail(new,'mapping_review',max_attempts=1,retry_seconds=0)
        self.assertEqual(self.inbox.status(),[('dead','mapping_review',1)])
        self.inbox.replay(('woocommerce','synthetic',received['event_id']))
        self.assertEqual(self.inbox.status(),[('pending',None,1)])

    def test_explicit_financial_reference_refresh_does_not_replay_order(self):
        from types import SimpleNamespace
        self.receive();key=('woocommerce','synthetic','10')
        target=SimpleNamespace(resolve=lambda event:{'sales_order':'SYNTHETIC-SO',
            'sales_invoice':'SYNTHETIC-SI','payment_entry':'SYNTHETIC-PE'})
        with self.assertRaises(ValueError):reconcile_order(self.inbox,self.mp,target,key)
        deliver_one(self.inbox,self.mp,lambda event,mp:{'sales_order':'SYNTHETIC-SO'})
        for _ in range(2):self.assertTrue(reconcile_order(self.inbox,self.mp,target,key)['reconciled'])
        with self.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM mp_commerce_events').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT sum(quantity) FROM mp_commerce_reservations').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT sales_invoice,payment_entry FROM mp_commerce_erp_links').fetchone(),('SYNTHETIC-SI','SYNTHETIC-PE'))
            raw=db.execute('SELECT raw_body FROM commerce_inbox').fetchone()[0]
            self.assertEqual(json.loads(raw)['id'],10)


    def pilot_config(self, product_id='1'):
        return dict(pilot_items={'ERP-SYN-1'}, gateways={'': 'manual_unpaid'},
                    mappings={str(product_id): dict(sku='NATIVE-WOO-SYN',
                        ecommerce_id=self.ecommerce, erp_item_code='ERP-SYN-1')})

    def test_retry_blocks_later_snapshot_and_same_second_update_requires_review(self):
        self.receive(status='pending')
        self.receive(status='cancelled')  # distinct source content, same Woo second
        def failed_erp(*_):
            raise TimeoutError('synthetic ERP timeout')
        deliver_one(self.inbox, self.mp, failed_erp, retry_seconds=30)
        self.assertFalse(deliver_one(self.inbox, self.mp, failed_erp))
        with self.connect() as db:
            db.execute("UPDATE commerce_delivery SET next_attempt_at=now()")
            self.assertEqual(db.execute('SELECT count(*) FROM mp_commerce_events').fetchone()[0], 1)
        erp = lambda *_: {'sales_order': 'SYNTHETIC-SO'}
        deliver_one(self.inbox, self.mp, erp)
        deliver_one(self.inbox, self.mp, lambda *_: self.fail('Conflicted order reached ERP'))
        self.assertEqual(self.inbox.status(), [('dead', 'revision_conflict', 1), ('done', None, 1)])
        self.assertEqual(self.available(), 1)
        self.receive(status='cancelled', date_modified_gmt='2026-10-30T10:00:02')
        deliver_one(self.inbox, self.mp, erp)
        self.assertEqual(self.available(), 2)
        self.receive(status='on-hold', date_modified_gmt='2026-10-30T10:00:01')
        deliver_one(self.inbox, self.mp, lambda *_: self.fail('Stale order reached ERP'))
        self.assertEqual(self.inbox.order_status(('woocommerce', 'synthetic', '10'))[-1]['erp'],
                         {'status': 'stale_skipped'})

    def test_deferred_mapping_review_can_replay_original_receipt(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tests'))
        from test_commerce_order_pilot import fixture, sign, SECRET
        raw = json.dumps(fixture()).encode()
        with self.connect() as db:
            db.execute("UPDATE ecommerce SET external_sku='NATIVE-WOO-SYN', external_product_id='1' WHERE nocopk=%s",
                       (self.ecommerce,))
        config = self.pilot_config()
        denied = dict(config, mappings={})
        erp = ReviewedERP('https://erp-test.danks.store', '', {
            'woocommerce|synthetic|10': {'customer': 'SYN-GUEST'}},
            lambda *_: {'message': {'sales_order': 'SYNTHETIC-SO'}})
        original = self.inbox.receive(raw, sign(raw), site='synthetic',
                                      unpaid_pilot=True, secrets=[SECRET])
        key = ('woocommerce', 'synthetic', '10')
        deliver_one(self.inbox, self.mp, erp, pilot_configs={'synthetic': denied})
        self.assertEqual(self.inbox.order_status(key)[0]['last_error'], 'item_unmapped')
        self.assertEqual(self.available(), 2)
        self.inbox.replay(('woocommerce', 'synthetic', original['event_id']))
        deliver_one(self.inbox, self.mp, erp, pilot_configs={'synthetic': config})
        self.assertEqual(self.inbox.order_status(key)[0]['state'], 'done')
        self.assertTrue(self.inbox.receive(raw, sign(raw), site='synthetic',
                                         unpaid_pilot=True, secrets=[SECRET])['duplicate'])
        self.assertEqual(self.available(), 1)

    @unittest.skipUnless(os.environ.get('COMMERCE_WP_CLI'), 'Disposable native Woo CLI not configured')
    def test_native_woo_order_created_updated_and_cancel(self):
        site = 'shop-test.danks.store'
        secret = 'synthetic-native-woocommerce-webhook-secret'
        app = application(self.inbox, {site: dict(unpaid_pilot=True, secrets=[secret])})
        def wp(*args):
            result = subprocess.run([os.environ['COMMERCE_WP_CLI'], *args],
                                    capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            return result.stdout
        with self.connect() as db:
            db.execute('UPDATE ecommerce SET site_key=%s WHERE nocopk=%s', (site, self.ecommerce))
        try:
            with make_server('127.0.0.1', 8100, app) as server:
                worker = Thread(target=server.serve_forever, daemon=True)
                worker.start()
                try:
                    fixture_path = str(Path(__file__).with_name('test_native_woo.php').resolve())
                    wp('eval-file', fixture_path, 'prepare')
                    fixture_order = json.loads(wp('eval-file', fixture_path, 'create'))
                    created = json.loads(wp('eval-file', fixture_path, 'deliver'))
                    self.assertIn({'topic': 'order.created', 'status': 202, 'error': None}, created)
                    self.assertTrue(all(entry['status'] == 202 for entry in created), created)
                    order_id = str(fixture_order['id'])
                    key = ('woocommerce', site, order_id)
                    erp_calls = []
                    def request(url, auth, method, body):
                        erp_calls.append(json.loads(body['payload']))
                        return {'message': {'sales_order': 'SYNTHETIC-WOO-SO'}}
                    target = ReviewedERP('https://erp-test.danks.store', '', {
                        '|'.join(key): {'customer': 'SYN-GUEST'}}, request)
                    config = {site: self.pilot_config(fixture_order['product'])}
                    with self.connect() as db:
                        db.execute("UPDATE ecommerce SET external_sku='NATIVE-WOO-SYN', external_product_id=%s WHERE nocopk=%s",
                                   (str(fixture_order['product']), self.ecommerce))
                    while deliver_one(self.inbox, self.mp, target, site=site, pilot_configs=config):
                        pass
                    accepted = self.inbox.order_status(key)
                    self.assertEqual(len(accepted), 1, accepted)
                    self.assertTrue(all(receipt['state'] == 'done' for receipt in accepted), accepted)
                    self.assertEqual(erp_calls[0]['event']['status'], 'pending')
                    with self.connect() as db:
                        event_id = accepted[0]['event_id']
                        raw = bytes(db.execute('SELECT raw_body FROM commerce_inbox WHERE event_id=%s',
                                               (event_id,)).fetchone()[0])
                        self.assertEqual(db.execute('SELECT sum(quantity) FROM mp_commerce_reservations').fetchone()[0], 1)
                    signature = base64.b64encode(hmac.digest(secret.encode(), raw, 'sha256')).decode()
                    from urllib.request import Request, urlopen
                    from urllib.error import HTTPError
                    url = 'http://127.0.0.1:8100/webhooks/woocommerce/' + site
                    for signed, expected in ((signature, 202), ('invalid', 400)):
                        req = Request(url, data=raw, headers={'Content-Type': 'application/json',
                                                              'X-WC-Webhook-Signature': signed})
                        try:
                            with urlopen(req) as resp:
                                self.assertEqual(resp.status, expected)
                                self.assertEqual(json.load(resp), {'event_id': event_id, 'duplicate': True})
                        except HTTPError as exc:
                            self.assertEqual(exc.code, expected)
                    self.assertEqual(self.inbox.order_status(key), accepted)
                    time.sleep(1.05)  # Separate source revisions for the cancellation acceptance.
                    wp('eval-file', fixture_path, 'cancel', order_id)
                    updated = json.loads(wp('eval-file', fixture_path, 'deliver'))
                    self.assertIn({'topic': 'order.updated', 'status': 202, 'error': None}, updated)
                    self.assertTrue(all(entry['status'] == 202 for entry in updated), updated)
                    while deliver_one(self.inbox, self.mp, target, site=site, pilot_configs=config):
                        pass
                    receipts = self.inbox.order_status(key)
                    self.assertEqual(len(receipts), 2, receipts)
                    self.assertTrue(all(receipt['state'] == 'done' for receipt in receipts), receipts)
                    self.assertEqual(erp_calls[-1]['event']['status'], 'cancelled')
                    with self.connect() as db:
                        self.assertEqual(db.execute('SELECT count(*) FROM mp_commerce_reservations').fetchone()[0], 0)
                        self.assertEqual(db.execute('SELECT count(*) FROM mp_commerce_orders').fetchone()[0], 1)
                        self.assertEqual(db.execute('SELECT sales_order FROM mp_commerce_erp_links').fetchone()[0],
                                         'SYNTHETIC-WOO-SO')
                    print('Native Woo fixture:', order_id, 'receipts:', [row['event_id'] for row in receipts])
                finally:
                    server.shutdown()
                    worker.join()
        finally:
            with self.connect() as db:
                db.execute("UPDATE ecommerce SET site_key='synthetic' WHERE nocopk=%s", (self.ecommerce,))

    def available(self):
        with self.connect() as db:
            # The existing channel snapshot joins gross stock to reservation-adjusted
            # stock. Never replace its raw inventory function or subtract twice.
            return db.execute("SELECT r.available_quantity FROM mp_ecommerce_catalog_inventory() c JOIN mp_commerce_inventory() r USING(ecommerce_id) WHERE c.ecommerce_id=%s",(self.ecommerce,)).fetchone()[0]

    def test_paid_at_creation_and_pending_both_reserve_then_cancel_releases(self):
        for initial in ('processing','pending'):
            with self.subTest(initial=initial):
                self.setUp()
                self.assertEqual(self.available(),2)
                first=self.receive(status=initial)
                self.assertTrue(deliver_one(self.inbox,self.mp,lambda event,mp:{'sales_order':'SYNTHETIC-SO'}))
                self.assertEqual(self.available(),1)
                self.assertTrue(self.receive(status=initial)['duplicate'])
                self.assertFalse(deliver_one(self.inbox,self.mp,lambda *_:self.fail('Duplicate delivered')))
                self.receive(status='cancelled',date_modified_gmt='2026-10-30T10:00:02')
                deliver_one(self.inbox,self.mp,lambda event,mp:{'sales_order':'SYNTHETIC-SO'})
                self.assertEqual(self.available(),2)
                with self.connect() as db:
                    self.assertEqual(db.execute('SELECT count(*) FROM mp_commerce_orders').fetchone()[0],1)
                    self.assertEqual(db.execute('SELECT count(*) FROM mp_commerce_events').fetchone()[0],2)
                    self.assertEqual(db.execute('SELECT storage_location_id FROM products WHERE item_id=%s LIMIT 1',(self.item,)).fetchone()[0],self.storage)

    def test_partial_shipment_then_cancel_preserves_physical_history(self):
        lines=[{'id':1,'product_id':1,'variation_id':0,'sku':'SYN-1','quantity':2}]
        self.receive(line_items=lines)
        # ERP references and payment evidence below are explicit contract mocks,
        # not proof of submitted ERP documents or Clover sandbox transactions.
        deliver_one(self.inbox,self.mp,lambda event,mp:{'sales_order':'SYNTHETIC-SO','sales_invoice':'SYNTHETIC-SI','payment_entry':'SYNTHETIC-PE'})
        self.assertEqual(self.available(),0)
        evidence={'provider':'woocommerce','site_key':'synthetic','external_order_id':'10','processor':'clover','verification':'verified_adapter','state':'captured','payment_id':'fixture-capture','currency':'USD','captured_amount':'12.00','refunded_amount':'0'}
        with self.connect() as db:
            db.execute('SELECT mp_commerce_match_payment(%s::jsonb)',(json.dumps(evidence),))
            db.execute("SELECT mp_commerce_confirm_reservation('woocommerce','synthetic','10')")
            product=db.execute('SELECT nocopk FROM products WHERE item_id=%s ORDER BY nocopk LIMIT 1',(self.item,)).fetchone()[0]
            shipped=db.execute("INSERT INTO locations(name,active,type) VALUES('Shipped',true,'Terminal') RETURNING nocopk").fetchone()[0]
        ack=json.dumps([{'line_id':'1','product_ids':[product]}])
        with self.assertRaisesRegex(Exception,'physically shipped'):
            with self.connect() as db:db.execute("SELECT mp_commerce_acknowledge_products('woocommerce','synthetic','10','fixture-movement',%s::jsonb)",(ack,))
        with self.connect() as db:
            # Explicit operator movement in this empty synthetic database, outside
            # webhook ingestion; storefront events never perform this update.
            db.execute('UPDATE products SET storage_location_id=%s WHERE nocopk=%s',(shipped,product))
            for expected in ('partial','duplicate'):
                self.assertEqual(db.execute("SELECT mp_commerce_acknowledge_products('woocommerce','synthetic','10','fixture-movement',%s::jsonb)",(ack,)).fetchone()[0],expected)
        self.receive(line_items=lines,date_modified_gmt='2026-10-30T10:00:01')
        deliver_one(self.inbox,self.mp,lambda event,mp:{'sales_order':'SYNTHETIC-SO','sales_invoice':'SYNTHETIC-SI','payment_entry':'SYNTHETIC-PE'})
        self.assertEqual(self.available(),0)
        self.receive(status='cancelled',line_items=lines,date_modified_gmt='2026-10-30T10:00:02')
        deliver_one(self.inbox,self.mp,lambda event,mp:{'sales_order':'SYNTHETIC-SO','sales_invoice':'SYNTHETIC-SI','payment_entry':'SYNTHETIC-PE'})
        self.assertEqual(self.available(),1)
        with self.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM mp_commerce_shipped_products').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT storage_location_id FROM products WHERE nocopk=%s',(product,)).fetchone()[0],shipped)
            self.assertEqual(db.execute('SELECT count(*) FROM mp_commerce_reservations').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM mp_commerce_orders').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT count(*) FROM mp_commerce_erp_links').fetchone()[0],1)

if __name__=='__main__':unittest.main()
