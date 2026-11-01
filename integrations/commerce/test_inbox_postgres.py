"""Native integration tests; invoked only with a disposable commerce_test DSN."""
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import hmac
import json
import os
from pathlib import Path
import unittest
from inbox import Inbox,PostgresInventory,deliver_one,reconcile_order
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
