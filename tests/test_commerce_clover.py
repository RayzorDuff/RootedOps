import base64
import copy
import hmac
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock,MagicMock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/commerce'))
from clover_sandbox import CloverSandboxEvidence,get_charge
from orders import normalize_woo

class CloverSandboxTests(unittest.TestCase):
    def setUp(self):
        self.secret='synthetic-sandbox-key-not-a-real-credential'
        self.order={'site_key':'synthetic','external_order_id':'10','external_order_number':'WEB010',
            'payment_processor':'clover','processor_payment_id':'charge-synthetic','currency':'USD','total':'15.00','refunds':[]}
        self.charge={'object':'charge','id':'charge-synthetic','livemode':False,'external_reference_id':'WEB010',
            'status':'succeeded','paid':True,'captured':True,'currency':'usd','amount':1500,'amount_captured':1500,'amount_refunded':0,
            'source':{'id':'synthetic-private-token'}}
        self.transport=Mock(side_effect=lambda *_:copy.deepcopy(self.charge))
        self.client=CloverSandboxEvidence(site_key='synthetic',merchant_id='SYNTHETIC',private_key=self.secret,enabled=True,transport=self.transport)
    def evidence(self,order=None):return self.client.evidence(order or self.order,reviewed_order={'id':'10','number':'WEB010'})
    def test_authenticated_charge_binding_omits_card_payload(self):
        evidence=self.evidence();self.assertEqual(evidence['captured_amount'],'15.00')
        self.assertEqual(evidence['external_order_id'],'10');self.assertEqual(evidence['external_order_number'],'WEB010')
        self.assertEqual(evidence['processor_reference_type'],'clover_ecommerce_charge')
        self.assertNotIn('source',evidence);self.assertNotIn(self.secret,json.dumps(evidence))
        self.transport.assert_called_once_with('charge-synthetic',self.secret)
    def test_declined_authorized_live_missing_and_ambiguous_refuse(self):
        for key,value in [('captured',False),('paid',False),('status','failed'),('livemode',True),('livemode',None),
                          ('id','another-charge'),('external_reference_id','10'),('currency','cad'),('amount_captured',1499),
                          ('amount',True),('amount_refunded',1),('object','list')]:
            old=copy.deepcopy(self.charge);self.charge[key]=value
            with self.assertRaises(ValueError,msg=key):self.evidence()
            self.charge=old
        del self.charge['amount_captured']
        with self.assertRaises(ValueError):self.evidence()
    def test_refunds_reconcile_exactly_without_implicit_restock(self):
        self.charge['amount_refunded']=500
        event=dict(self.order,refunds=[{'external_refund_id':'woo-refund-synthetic','amount':'5.00'}])
        evidence=self.evidence(event);self.assertEqual(evidence['refunded_amount'],'5.00');self.assertNotIn('restock',evidence)
        self.charge['amount_refunded']=1500;event['refunds'][0]['amount']='15.00'
        self.assertEqual(self.evidence(event)['refunded_amount'],'15.00')
    def test_scope_and_source_id_checks_happen_before_transport(self):
        for edits in ({'site_key':'other'},{'processor_payment_id':'../../other'},{'external_order_id':'different'}):
            with self.assertRaises(ValueError):self.evidence(dict(self.order,**edits))
        self.transport.assert_not_called()
        with self.assertRaises(ValueError):get_charge('../invalid',self.secret)
        with self.assertRaises(ValueError):CloverSandboxEvidence(site_key='synthetic',merchant_id='SYNTHETIC',private_key=self.secret)
    def test_provider_failure_is_redacted(self):
        self.transport.side_effect=RuntimeError(self.secret)
        with self.assertRaises(RuntimeError) as caught:self.evidence()
        self.assertNotIn(self.secret,str(caught.exception));self.assertTrue(caught.exception.__suppress_context__)
    def test_http_boundary_is_fixed_sandbox_get_and_refuses_ambiguous_json(self):
        response=MagicMock();response.__enter__.return_value=response
        response.read.return_value=json.dumps(self.charge).encode()
        opener=Mock();opener.open.return_value=response
        with patch('clover_sandbox.build_opener',return_value=opener):
            self.assertEqual(get_charge('charge-synthetic',self.secret)['id'],'charge-synthetic')
            request=opener.open.call_args.args[0]
            self.assertEqual(request.get_method(),'GET')
            self.assertEqual(request.full_url,'https://scl-sandbox.dev.clover.com/v1/charges/charge-synthetic')
            self.assertEqual(request.get_header('Authorization'),'Bearer '+self.secret)
            response.read.return_value=b'{"id":"first","id":"second"}'
            with self.assertRaises(RuntimeError):get_charge('charge-synthetic',self.secret)
    def test_equivalent_decimal_scales_reconcile_without_rounding(self):
        self.assertEqual(self.evidence(dict(self.order,total='15'))['captured_amount'],'15.00')
        with self.assertRaises(ValueError):self.evidence(dict(self.order,total='15.001'))
    def test_official_gateway_and_display_number_remain_unverified(self):
        source={'id':10,'number':'WEB010','status':'on-hold','currency':'USD','total':'15.00',
            'date_modified_gmt':'2026-10-31T10:00:00','payment_method':'clover_payments','transaction_id':'charge-synthetic',
            'line_items':[{'id':8,'product_id':1,'variation_id':0,'sku':'SYN-001','quantity':1}],'refunds':[]}
        raw=json.dumps(source).encode();secret='synthetic-webhook-secret-not-a-real-credential';signature=base64.b64encode(hmac.digest(secret.encode(),raw,'sha256')).decode()
        event=normalize_woo(raw,signature,[secret],'synthetic',{'1':{'sku':'SYN-001','ecommerce_id':1,'erp_item_code':'SYN-001'}},{'clover_payments':'clover'})
        self.assertEqual(event['external_order_id'],'10');self.assertNotIn('external_order_number',event)
        self.assertEqual(event['reconciliation_status'],'unverified');self.assertEqual(event['status'],'on-hold')

if __name__=='__main__':unittest.main()
