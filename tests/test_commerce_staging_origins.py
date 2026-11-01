import base64
import hmac
import json
from pathlib import Path
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'integrations/commerce')]
from staging_origin import staging_origin,staging_pair
from commerce_staging_targets import targets
from inbox import ReviewedERP,PostgresInventory
from channel import upsert_draft
from orders import normalize_woo


class StagingOriginTests(unittest.TestCase):
    def test_exact_origins_and_cross_environment_refusal(self):
        for suffix in ('test','test2'):
            erp='https://erp-'+suffix+'.danks.store';shop='https://shop-'+suffix+'.danks.store'
            self.assertEqual(staging_pair(erp+'/',shop+':443'),(erp,shop))
        with self.assertRaises(ValueError):staging_pair('https://erp-test.danks.store','https://shop-test2.danks.store')
        for value in ('https://shop.danks.store','https://shop-test2.danks.store.evil.invalid','http://shop-test2.danks.store',
                      'https://user:secret@shop-test2.danks.store','https://shop-test2.danks.store:444',
                      'https://shop-test2.danks.store/path','https://shop-test2.danks.store?x=y','https://shop-test2.danks.store#fragment'):
            with self.subTest(value=value),self.assertRaises(ValueError):staging_origin(value,'shop')

    def test_receipt_and_environment_must_match(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory);(p/'TEST_ENVIRONMENT').write_text('rootedops-full-test')
            (p/'receipt.json').write_text(json.dumps({'hostname_suffix':'-test2'}))
            (p/'.env').write_text('ERPNEXT_SITE_NAME=erp-test2.danks.store\n')
            self.assertEqual(targets(p)['shop'],'https://shop-test2.danks.store')
            (p/'.env').write_text('ERPNEXT_SITE_NAME=erp-test.danks.store\n')
            with self.assertRaises(ValueError):targets(p)

    def test_erp_identity_link_uses_configured_site(self):
        payloads=[]
        class DB:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def execute(self,sql,params):payloads.append(json.loads(params[0]));return self
            def fetchone(self):return ({'status':'linked'},)
        erp=ReviewedERP('https://erp-test2.danks.store/',None,{},None)
        self.assertEqual(erp.base,'https://erp-test2.danks.store')
        target=PostgresInventory(DB,erp_site='erp-test2.danks.store')
        target.link_erp({'provider':'woocommerce','site_key':'synthetic','external_order_id':'1'},{'sales_order':'SYN-SO'})
        self.assertEqual(payloads[0]['erp_site'],'erp-test2.danks.store')
        with self.assertRaises(ValueError):PostgresInventory(None,erp_site='erp.danks.store')

    def test_invalid_shop_target_never_calls_transport(self):
        calls=[]
        with self.assertRaises(ValueError):upsert_draft('http://shop-test2.danks.store','secret',{},request=lambda *a:calls.append(a))
        self.assertEqual(calls,[])


class PaidCreationTests(unittest.TestCase):
    def normalize(self,status,second=0):
        order={'id':123,'status':status,'date_modified_gmt':'2026-10-31T12:00:'+str(second).zfill(2),
            'currency':'USD','payment_method':'clover_payments','transaction_id':'synthetic-charge' if status=='processing' else '',
            'total':'12.50','line_items':[{'id':1,'product_id':10,'variation_id':0,'sku':'SYN','quantity':2}]}
        raw=json.dumps(order).encode();secret='s'*32
        signature=base64.b64encode(hmac.digest(secret.encode(),raw,'sha256')).decode()
        return normalize_woo(raw,signature,[secret],'synthetic-test2',{'10':{'sku':'SYN','ecommerce_id':1,'erp_item_code':'SYN'}},{'clover_payments':'clover'})

    def test_initial_paid_order_is_ingested_without_prior_pending_event(self):
        event=self.normalize('processing')
        self.assertEqual(event['external_order_id'],'123');self.assertEqual(event['lines'][0]['quantity'],2)
        self.assertEqual(event['status'],'processing');self.assertEqual(event['reconciliation_status'],'unverified')
        self.assertFalse(event['fulfillment_requested'])
        self.assertEqual(event['event_id'],self.normalize('processing')['event_id'])

    def test_pending_intake_and_paid_transition_preserve_order_identity(self):
        pending=self.normalize('pending');paid=self.normalize('processing',1)
        self.assertEqual(pending['external_order_id'],paid['external_order_id'])
        self.assertEqual(pending['lines'],paid['lines']);self.assertEqual(pending['status'],'pending')
        self.assertGreater(paid['revision'],pending['revision']);self.assertNotEqual(paid['event_id'],pending['event_id'])


if __name__=='__main__':unittest.main()
