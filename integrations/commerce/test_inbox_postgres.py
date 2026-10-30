"""Native integration tests; invoked only with a disposable commerce_test DSN."""
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import hmac
import json
import os
from pathlib import Path
import unittest
from inbox import Inbox,PostgresInventory,deliver_one
from runtime import connect_test

class NativeInboxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.connect=staticmethod(connect_test(os.environ['COMMERCE_INBOX_DSN']))
        with cls.connect() as db:
            db.execute(Path(__file__).with_name('inbox.sql').read_text())
            db.execute('CREATE TABLE erp_draft_probe(source_key text PRIMARY KEY)')
            cls.item=db.execute("INSERT INTO items(item_id,name,category,active) VALUES('INBOX-SYNTHETIC','Synthetic','grain',true) RETURNING nocopk").fetchone()[0]
            loc=db.execute("INSERT INTO locations(name,active,type) VALUES('Inbox synthetic',true,'Storage') RETURNING nocopk").fetchone()[0]
            db.execute('INSERT INTO products(item_id,storage_location_id,use_by) VALUES(%s,%s,CURRENT_DATE+1),(%s,%s,CURRENT_DATE+1)',(cls.item,loc,cls.item,loc))
            cls.ecommerce=db.execute("INSERT INTO ecommerce(name,item_id,provider,site_key,external_sku,erp_item_code,sync_enabled,status) VALUES('Inbox synthetic',%s,'woocommerce','synthetic','SYN-1','ERP-SYN-1',true,'Sterilized') RETURNING nocopk",(cls.item,)).fetchone()[0]
    def setUp(self):
        with self.connect() as db:
            for table in ['commerce_delivery','commerce_inbox','erp_draft_probe','mp_commerce_payment_matches','mp_commerce_events','mp_commerce_reservations','mp_commerce_orders']:
                db.execute('DELETE FROM '+table)
        self.inbox=Inbox(self.connect);self.mp=PostgresInventory(self.connect)
    def receive(self):
        raw=json.dumps({'id':10,'status':'processing','currency':'USD','total':'12.00','date_modified_gmt':'2026-10-30T10:00:00',
            'payment_method':'clover_test','transaction_id':'fixture-capture','line_items':[{'id':1,'product_id':1,'variation_id':0,'sku':'SYN-1','quantity':1}],'refunds':[]}).encode()
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

if __name__=='__main__':unittest.main()
