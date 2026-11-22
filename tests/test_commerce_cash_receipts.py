"""Explicit cash evidence and destination recovery; no cash inferred from shipping."""
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/commerce'))
from cash_reconciliation import packet, reconcile, canonical

RID='61382727-2fd1-450a-b03a-832a343fce5c'
SNAPSHOT={'items':[{'id':1,'sku':'SYN-1','productId':91,'quantity':1}],'total':10,'currency':'USD'}
RECEIPT=dict(receipt_id=RID,provider='ecwid',site_key='dank_mushrooms',external_order_id='10',amount=Decimal('10'),currency='USD',received_at=datetime(2026,11,21,tzinfo=timezone.utc),operator='operator@example.invalid',snapshot=SNAPSHOT)
APPROVAL=dict(enabled=True,source_key='ecwid|dank_mushrooms|10',source_fingerprint=hashlib.sha256(canonical(SNAPSHOT)).hexdigest(),lines=[dict(line_id='1',source_sku='SYN-1',external_product_id='91',erp_item_code='ERP-SYN-1',quantity=1)])
class CashTests(unittest.TestCase):
 def test_packet_is_separate_from_clover_and_requires_exact_map(self):
  data=packet(RECEIPT,APPROVAL)
  self.assertEqual(data['processor'],'cash');self.assertEqual(data['state'],'received')
  self.assertNotIn('merchant_id',data);self.assertNotIn('payment_id',data)
  with self.assertRaises(ValueError):packet(RECEIPT,dict(APPROVAL,enabled=False))
  with self.assertRaises(ValueError):packet(RECEIPT,dict(APPROVAL,source_fingerprint='changed'))
  bad=dict(APPROVAL,lines=[dict(APPROVAL['lines'][0],source_sku='WRONG')])
  with self.assertRaises(ValueError):packet(RECEIPT,bad)
 def test_cash_order_status_is_not_payment_evidence(self):
  from test_commerce_order_pilot import fixture, SITE
  from orders import normalize_order, woo_source, OrderReview
  order=fixture();order.update(payment_method='cod',status='processing',prices_include_tax=False,date_created_gmt='2026-11-21T12:00:00')
  raw,identity=woo_source(json.dumps(order).encode(),SITE,'synthetic-cash')
  config=dict(mappings={'1':dict(sku='NATIVE-WOO-SYN',ecommerce_id=1,erp_item_code='ITEM')},gateways={'cod':'cash'},pilot_items={'ITEM'},reviewed_mapping=True)
  with self.assertRaises(OrderReview):normalize_order(raw,identity,**config)
  event=normalize_order(raw,identity,**config,cash_receipt_pilot=True)
  self.assertEqual(event['payment_processor'],'cash');self.assertEqual(event['reconciliation_status'],'unverified')
  self.assertIsNone(event['processor_payment_id'])
  order['transaction_id']='a-card-reference';raw,identity=woo_source(json.dumps(order).encode(),SITE,'bad')
  with self.assertRaises(OrderReview):normalize_order(raw,identity,**config,cash_receipt_pilot=True)
 def test_erp_commit_then_mp_timeout_retries_same_receipt(self):
  state={'fail_ack':True};calls=[]
  class Row:
   def fetchone(self):return tuple(RECEIPT[k] for k in ('provider','site_key','external_order_id','amount','currency','received_at','operator','snapshot'))
  class DB:
   def __enter__(self):return self
   def __exit__(self,*args):pass
   def execute(self,sql,args):
    if 'ack_cash' in sql and state['fail_ack']:
     state['fail_ack']=False;raise TimeoutError('MP ack timeout')
    return Row()
  config=dict(enabled=True,production=True,erp_origin='https://erp.danks.store',approved_receipts={RID:APPROVAL})
  def request(url,auth,verb,payload):
   calls.append(json.loads(payload['payload']));return {'message':dict(sales_order='SYN-SO',sales_invoice='SYN-SI',payment_entry='SYN-PE')}
  with patch.dict(os.environ,ERP_AUTHORIZATION='synthetic',COMMERCE_CASH_EVIDENCE_KEY='synthetic-cash-proof-key-32-characters'), patch('cash_reconciliation.check_current_source'):
   with self.assertRaises(TimeoutError):reconcile(DB,RID,config,request=request)
   result=reconcile(DB,RID,config,request=request)
  self.assertEqual(result['status'],'accounted');self.assertEqual(calls[0],calls[1]);self.assertEqual(calls[0]['receipt_id'],RID)
 def test_disabled_posting_never_calls_erp(self):
  with self.assertRaisesRegex(ValueError,'disabled'):
   reconcile(lambda:self.fail('DB should not be opened'),RID,dict(enabled=False,erp_origin='https://erp.danks.store'))
if __name__=='__main__':unittest.main()

class CashConfigTests(unittest.TestCase):
 def test_pause_preserves_existing_site_credentials_and_approvals(self):
  import importlib.util
  spec=importlib.util.spec_from_file_location('cash_config',Path(__file__).resolve().parents[1]/'scripts/commerce_cash_config.py')
  module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  original={'db_password':'synthetic','commerce_cash_accounting':{'enabled':True,'approved_orders':{'source':{'enabled':True}},'evidence_hmac':'synthetic'}}
  result=module.merge(original,{'enabled':False})
  self.assertEqual(result['db_password'],'synthetic');self.assertIn('source',result['commerce_cash_accounting']['approved_orders'])
  self.assertTrue(original['commerce_cash_accounting']['enabled'])
  with self.assertRaises(ValueError):module.merge(original,{'enabled':True})
