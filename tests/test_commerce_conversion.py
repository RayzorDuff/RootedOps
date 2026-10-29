"""Synthetic offline catalog, customer/order, webhook and payment contracts."""
import base64
from copy import deepcopy
import hashlib
import hmac
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'integrations/commerce'))
from ecwid_migrate import plan, digest
from reviewed_catalog import compile_catalog
from history import convert_history, identity
from orders import authenticate, normalize_woo, reconcile_clover
from channel import draft_payload


def catalog_fixture():
    source = {'store_id':'synthetic','products':[{'id':1,'sku':'001','name':'Culture',
        'price':'12.50','categoryIds':[3],'_combinations':[{'id':2,'sku':'001-20','price':'15.00',
        'options':[{'name':'Volume','value':'20 ml'}]}]}]}
    p = plan(source)
    review = {'source_sha256':p['source_sha256'],'currency':'USD','currency_confirmed':True,
        'selling_price_list':'Synthetic USD',
        'items':{sku:{'item_code':'ERP-'+sku,'item_group':'Cultures','stock_uom':'Nos',
                     'tax_key':'standard','attributes':['Volume']} for sku in ['001','001-20']},
        'categories':{'3':{'woocommerce_id':9}},
        'attributes':{'Volume':{'erp_attribute':'Volume','woocommerce_name':'Volume','values':['20 ml']}},
        'taxes':{'standard':{'woocommerce_status':'taxable','woocommerce_class':'',
                             'erp_item_tax_template':'Synthetic Sales Tax'}}}
    return p, review


class CatalogConversionTests(unittest.TestCase):
    def test_template_leaf_price_tax_category_and_variation(self):
        p,r=catalog_fixture(); result=compile_catalog(p,r)
        template,leaf=result['records']
        self.assertEqual(template['item']['has_variants'],1)
        self.assertIsNone(template['price'])
        self.assertEqual(leaf['item']['variant_of'],'ERP-001')
        self.assertEqual(leaf['price']['item_price_rate'],'15.00')
        self.assertEqual(leaf['woocommerce']['categories'],[{'id':9}])
        self.assertEqual(leaf['item']['taxes'],[{'item_tax_template':'Synthetic Sales Tax'}])
        body=draft_payload(leaf, parent_id=4, attributes=leaf['variant_attributes'])
        self.assertEqual(body['regular_price'],'15.00')
        self.assertEqual(body['attributes'],[{'name':'Volume','option':'20 ml'}])
        self.assertEqual(body['sku'],'001-20')
        self.assertEqual(body['status'],'draft')
        self.assertNotIn('stock_quantity',body)

    def test_source_review_currency_and_attribute_mismatch_fail(self):
        p,r=catalog_fixture()
        for mutate in [lambda x:x.update(source_sha256='wrong'),lambda x:x.update(currency_confirmed=False),
                       lambda x:x['attributes']['Volume'].update(values=['10 ml']),
                       lambda x:x['items']['001'].update(attributes=['Other'])]:
            changed=deepcopy(r);mutate(changed)
            with self.assertRaises((ValueError,KeyError)):compile_catalog(p,changed)

    def test_tax_and_price_errors_are_not_silently_defaulted(self):
        p,r=catalog_fixture();r['taxes']['standard']={'woocommerce_status':'taxable','woocommerce_class':''}
        with self.assertRaises(ValueError):compile_catalog(p,r)
        p,r=catalog_fixture();p['products'][1]['price']='NaN'
        with self.assertRaises(ValueError):compile_catalog(p,r)

    def test_remote_images_cannot_be_forwarded_without_archived_uploaded_manifest(self):
        p,r=catalog_fixture();p['products'][0]['content']['gallery']=[{'source_url':'https://cdn.example/a','image':'https://cdn.example/a'}]
        with self.assertRaises(ValueError):compile_catalog(p,r)
        media=[{'url':'https://cdn.example/a','sha256':'a'*64,'erp_file_url':'/files/a.png','woocommerce_media_id':12}]
        result=compile_catalog(p,r,media)
        self.assertEqual(result['records'][0]['content']['gallery'][0]['image'],'/files/a.png')
        self.assertEqual(result['records'][0]['woocommerce']['images'],[{'id':12}])


def history_fixture():
    source={'store_id':'synthetic','customers':[{'id':1,'name':'Synthetic Customer','email':'synthetic@example.invalid'}],
        'orders':[{'id':'ORDER-1','customerId':1,'currency':'USD','total':'12.00','createDate':'2026-10-01 12:00:00 +0000',
                   'items':[{'id':3,'sku':'001','quantity':2}]}]}
    review={'source_sha256':digest(source),'currency':'USD','company':'Synthetic Company','conversion_rate':1,
            'customer_group':'Individual','territory':'United States','selling_price_list':'Synthetic USD',
            'delivery_date':'2026-10-01','items':{'001':'ERP-001'},
            'orders':{'ORDER-1':{'lines':{'3':{'net_total':'10.00'}},
                'charges':[{'amount':'2.00','erp_account':'Synthetic Shipping','description':'Shipping'}]}}}
    return source,review


class HistoryConversionTests(unittest.TestCase):
    def test_draft_only_total_and_stable_scoped_identities(self):
        source,review=history_fixture(); result=convert_history(source,review)
        self.assertEqual(result,convert_history(source,review))
        self.assertEqual(result['orders'][0]['sales_order']['docstatus'],0)
        self.assertEqual(result['orders'][0]['sales_order']['items'][0]['rate'],'5.00')
        self.assertFalse(result['financial_replay']);self.assertFalse(result['fulfillment_replay'])
        self.assertNotEqual(identity('ecwid','a','customer',1),identity('ecwid','b','customer',1))

    def test_totals_identity_and_missing_currency_fail(self):
        source,r=history_fixture();r['orders']['ORDER-1']['lines']['3']['net_total']='9.00'
        with self.assertRaises(ValueError):convert_history(source,r)
        source,r=history_fixture();source['orders'][0].pop('currency');r['source_sha256']=digest(source)
        with self.assertRaises(KeyError):convert_history(source,r)


class WebhookTests(unittest.TestCase):
    secret='synthetic-fixture-secret-not-a-credential'
    def fixture(self):
        return {'id':10,'status':'processing','currency':'USD','total':'15.00',
                'date_modified_gmt':'2026-10-29T10:00:00','payment_method':'reviewed_clover',
                'transaction_id':'capture-synthetic','line_items':[{'id':8,'product_id':1,'variation_id':2,'sku':'001-20','quantity':1}],
                'refunds':[]}
    def sign(self,raw):return base64.b64encode(hmac.digest(self.secret.encode(),raw,'sha256')).decode()
    def normalize(self,source=None):
        raw=json.dumps(source or self.fixture()).encode()
        return normalize_woo(raw,self.sign(raw),[self.secret],'synthetic',
                             {'2':{'sku':'001-20','ecommerce_id':4,'erp_item_code':'ERP-001-20'}},{'reviewed_clover':'clover'})
    def test_raw_bytes_signature_rotation_and_tamper(self):
        raw=json.dumps(self.fixture()).encode()
        self.assertEqual(authenticate(raw,self.sign(raw),['previous-synthetic-secret-aaaaaaaa',self.secret]),hashlib.sha256(raw).hexdigest())
        for changed,signature in [(raw+b' ',self.sign(raw)),(raw,'malformed!'),(raw,'')]:
            with self.assertRaises(ValueError):authenticate(changed,signature,[self.secret])
    def test_exact_product_variation_mapping_and_integer_quantity(self):
        self.assertEqual(self.normalize()['lines'][0]['ecommerce_id'],4)
        self.assertEqual(self.normalize()['reconciliation_status'],'unverified')
        for value in [True,1.5,0,-1,'1']:
            source=self.fixture();source['line_items'][0]['quantity']=value
            with self.assertRaises(ValueError):self.normalize(source)
        source=self.fixture();source['line_items'][0]['sku']='other'
        with self.assertRaises(ValueError):self.normalize(source)
    def test_currency_must_be_explicit_uppercase_iso_shape(self):
        for value in ('usd', 'US', '', None, 123):
            source=self.fixture();source['currency']=value
            with self.assertRaises(ValueError):self.normalize(source)

    def test_refunds_are_auditable_not_automatic_restock(self):
        source=self.fixture();source.update(status='refunded',refunds=[{'id':3,'total':'-15.00'}])
        normalized=self.normalize(source)
        self.assertEqual(normalized['refunds'],[{'external_refund_id':'3','amount':'15.00'}])
        self.assertNotIn('restock',normalized)
        source['refunds'][0]['total']='-14.00'
        with self.assertRaises(ValueError):self.normalize(source)
    def test_duplicate_json_and_lines_fail(self):
        raw=b'{"id":1,"id":2}'
        with self.assertRaises(ValueError):normalize_woo(raw,self.sign(raw),[self.secret],'synthetic',{}, {})
        source=self.fixture();source['line_items']*=2
        with self.assertRaises(ValueError):self.normalize(source)
    def test_capture_identity_currency_and_refund_reconciliation(self):
        order=self.normalize()
        evidence={'verification':'verified_adapter','processor':'clover','state':'captured',
            'site_key':'synthetic','external_order_id':'10','payment_id':'capture-synthetic',
            'currency':'USD','captured_amount':'15.00','refunded_amount':'0'}
        result=reconcile_clover(order,evidence)
        self.assertEqual(result['status'],'matched');self.assertFalse(result['create_payment_entry'])
        for key,value in [('state','authorized'),('payment_id','other'),('currency','CAD'),('captured_amount','14.99'),
                          ('refunded_amount','1.00'),('external_order_id','11'),('verification','webhook')]:
            with self.assertRaises(ValueError):reconcile_clover(order,dict(evidence,**{key:value}))


class SeoTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('php'),'PHP CLI unavailable locally; required in CI')
    def test_wordpress_and_yoast_hooks_escape_and_fallback(self):
        script=ROOT/'wordpress/rootedops-commerce/test-seo.php'
        subprocess.run(['php',str(script)],check=True)


class MediaUploadTests(unittest.TestCase):
    def test_verified_binary_receipts_retries_and_host_scope(self):
        import tempfile
        from media_upload import upload
        with tempfile.TemporaryDirectory() as directory:
            content=b'\x89PNG\r\n\x1a\nsynthetic-raster-fixture'
            sha=hashlib.sha256(content).hexdigest();Path(directory,sha).write_bytes(content)
            manifest=[{'url':'https://cdn.example/a','sha256':sha,'file':sha,'bytes':len(content),'content_type':'image/png'}]
            calls=[]
            def request(url,*args):
                calls.append(url)
                return {'message':{'file_url':'/files/synthetic.png'}} if '/upload_file' in url else {'id':12}
            args=(manifest,directory,Path(directory)/'receipts.json','https://erp-test.danks.store','https://shop-test.danks.store','unused','unused')
            first=upload(*args,request=request);second=upload(*args,request=request)
            self.assertEqual(first,second);self.assertEqual(len(calls),2)
            self.assertEqual(Path(directory,'receipts.json').stat().st_mode & 0o777,0o600)
            Path(directory,sha).write_bytes(b'corrupt')
            with self.assertRaises(ValueError):upload(*args,request=request)
            with self.assertRaises(ValueError):upload(manifest,directory,Path(directory)/'other','https://erp.danks.store',args[4],'unused','unused',request=request)

class FrappeHistoryBoundaryTests(unittest.TestCase):
    def module(self):
        from types import SimpleNamespace
        fake=SimpleNamespace(conf={},get_roles=lambda:['Sales Manager'],parse_json=lambda x:x,
                             whitelist=lambda **kwargs:lambda f:f)
        path=ROOT/'erpnext/apps/rootedops_commerce/rootedops_commerce/history.py'
        spec=importlib.util.spec_from_file_location('frappe_history_under_test',path)
        module=importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules,{'frappe':fake}):spec.loader.exec_module(module)
        return module,fake

    def test_disabled_site_cannot_import(self):
        module,_=self.module()
        with self.assertRaisesRegex(ValueError,'site configuration'):module.import_history({})

    def test_registry_retry_drift_and_submitted_history_refusal(self):
        from types import SimpleNamespace
        module,fake=self.module();store={};counts={}
        class Doc(SimpleNamespace):
            def check_permission(self,action):pass
            def insert(self):
                kind=self.doctype;counts[kind]=counts.get(kind,0)+1
                self.name=getattr(self,'source_key',kind+'-'+str(counts[kind]))
                store[(kind,self.name)]=self
                return self
        def get_doc(kind,name=None):
            if isinstance(kind,dict):return Doc(**kind)
            return store[(kind,name)]
        fake.get_doc=get_doc;fake.db=SimpleNamespace(exists=lambda kind,name:(kind,name) in store)
        row={'source_payload':{'id':'synthetic'}}
        first=module._ensure('key',row,'Customer',{'customer_name':'Synthetic'})
        second=module._ensure('key',row,'Customer',{'customer_name':'Synthetic'})
        self.assertEqual(first.name,second.name);self.assertEqual(counts['Customer'],1)
        self.assertIn('synthetic',store[('Commerce Migration Identity','key')].source_payload)
        with self.assertRaisesRegex(ValueError,'drift'):module._ensure('key',{'changed':True},'Customer',{})
        target=module._ensure('order',row,'Sales Order',{'docstatus':0})
        target.docstatus=1
        with self.assertRaisesRegex(ValueError,'submitted'):module._ensure('order',row,'Sales Order',{})

if __name__=='__main__':unittest.main()
