import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'integrations/commerce'))
from inbox import application,ReviewedERP
from runtime import connect_test

class ReceiverTests(unittest.TestCase):
    def test_refuses_insecure_nonlocal_routes_and_oversize_before_receipt(self):
        inbox=Mock();app=application(inbox,{'test':{}})
        for edits in ({'SERVER_NAME':'production.example'},{'CONTENT_LENGTH':'2097153'},
                      {'PATH_INFO':'/webhooks/woocommerce/unknown'},{'REQUEST_METHOD':'GET'}):
            env={'REQUEST_METHOD':'POST','SERVER_NAME':'127.0.0.1','wsgi.url_scheme':'http',
                 'PATH_INFO':'/webhooks/woocommerce/test','CONTENT_LENGTH':'2','CONTENT_TYPE':'application/json','wsgi.input':io.BytesIO(b'{}')}
            env.update(edits);statuses=[]
            app(env,lambda status,headers:statuses.append(status))
            self.assertTrue(statuses[0].startswith('400'))
        inbox.receive.assert_not_called()
    def test_durable_failure_returns_retryable_status_without_details(self):
        inbox=Mock();inbox.receive.side_effect=RuntimeError('secret-token')
        app=application(inbox,{'test':{'secrets':['x'*32],'mappings':{},'gateways':{}}});statuses=[]
        env={'REQUEST_METHOD':'POST','SERVER_NAME':'127.0.0.1','wsgi.url_scheme':'http',
             'PATH_INFO':'/webhooks/woocommerce/test','CONTENT_LENGTH':'2','CONTENT_TYPE':'application/json','wsgi.input':io.BytesIO(b'{}')}
        body=b''.join(app(env,lambda s,h:statuses.append(s)))
        self.assertTrue(statuses[0].startswith('503'));self.assertNotIn(b'secret',body)
    def test_erp_refuses_production(self):
        for url in ['https://erp.danks.store','http://erp-test.danks.store','https://user:pass@erp-test.danks.store']:
            with self.assertRaises(ValueError):ReviewedERP(url,'unused',{},Mock())


class ReviewTests(unittest.TestCase):
    def test_order_draft_math_and_inventory_identity(self):
        import importlib.util
        from types import SimpleNamespace
        path=ROOT/'erpnext/apps/rootedops_commerce/rootedops_commerce/order_service.py'
        spec=importlib.util.spec_from_file_location('order_service_contract',path);module=importlib.util.module_from_spec(spec)
        from unittest.mock import patch
        sys.path.insert(0,str(ROOT/'erpnext/apps/rootedops_commerce'))
        with patch.dict(sys.modules,{'frappe':SimpleNamespace(whitelist=lambda **kw:lambda f:f)}):spec.loader.exec_module(module)
        event={'currency':'USD','total':'12.00','lines':[{'erp_item_code':'SYN','quantity':2}]}
        values={'customer':'Synthetic','currency':'USD','items':[{'item_code':'SYN','qty':2,'rate':'5.00'}],
                'taxes':[{'charge_type':'Actual','account_head':'Synthetic tax','description':'Tax','tax_amount':'2.00'}],'docstatus':0}
        module.validate_draft(values,event)
        with self.assertRaises(ValueError):module.validate_draft(dict(values,docstatus=1),event)
        with self.assertRaises(ValueError):module.validate_draft(values,dict(event,total='13.00'))

    def test_woo_customer_ownership_and_test_mail_gate(self):
        from customers import upsert_customer
        from ecwid_migrate import digest
        reviewed={'email':'synthetic@example.invalid','first_name':'Synthetic'}
        with self.assertRaises(ValueError):upsert_customer('https://shop-test.danks.store','unused','source',reviewed)
        request=Mock(return_value=[{'id':1,'email':reviewed['email'],'meta_data':[]}])
        with self.assertRaises(ValueError):upsert_customer('https://shop-test.danks.store','unused','source',reviewed,mail_sink_verified=True,request=request)
        request.return_value=[{'id':1,'email':reviewed['email'],'meta_data':[{'key':'_rootedops_source_key','value':'source'},{'key':'_rootedops_customer_hash','value':digest(reviewed)}]}]
        self.assertFalse(upsert_customer('https://shop-test.danks.store','unused','source',reviewed,mail_sink_verified=True,request=request)['created'])

if __name__=='__main__':unittest.main()
