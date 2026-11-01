#!/usr/bin/env python3
"""Synthetic ERP service-layer → Woo draft proof; no MP stock or accounting writes."""
import argparse
import base64
import copy
import hashlib
import json
from decimal import Decimal
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'integrations/commerce'))
from commerce_staging_targets import targets
from ecwid_migrate import api,private_write
from channel import upsert_draft
from sync import prepare
from commerce_live_sync_smoke import verify_product

SKU='SYN-TEST2-ERP-CATALOG'
GROUP='RootedOps Test2 Commerce Fixtures'
PRICE_LIST='RootedOps Test2 USD'
SOURCE='synthetic:test2:erp-catalog:v1'


def run(environment, candidate_api=None, candidate_sha256=None):
    p=environment.resolve();resolved=targets(p)
    if resolved['erp']!='https://erp-test2.danks.store':raise ValueError('This synthetic fixture is Test2 only')
    private=p/'private'
    controls=json.loads((private/'wordpress-offline-receipt.json').read_text())['controls']
    if controls!={'cron_disabled':True,'http_blocked':True,'mail_blocked':True,'payment_gateways':0}:
        raise ValueError('Isolated shop required')
    installed=json.loads((p/'test2-readiness/erp-native-acceptance.json').read_text())
    # The receipt is required as a deployment precondition; live checks below verify apps/site.
    if not installed:raise ValueError('Native ERP installation evidence required')
    container=json.loads(subprocess.check_output(['docker','inspect','rootedops-full-test-erpnext-backend-1']))[0]
    labels=container['Config']['Labels']
    if (labels.get('com.docker.compose.project')!='rootedops-full-test'
        or labels.get('com.docker.compose.service')!='erpnext-backend'
        or not container['State']['Running']
        or container['Image']!='sha256:908a38651afd93e0e2823cfee7ce4c07db02293c072f6c006d2ea26c311d3438'
        or list(container['NetworkSettings']['Networks'])!=['rootedops-full-test_default']
        or any(v is not None for v in (container['NetworkSettings']['Ports'] or {}).values())):
        raise ValueError('Expected isolated restored ERP image/container required')
    network=json.loads(subprocess.check_output(['docker','network','inspect','rootedops-full-test_default']))[0]
    if network['Internal'] is not True:raise ValueError('Internal ERP network required')
    payload={'item':{'item_code':SKU,'item_name':'Synthetic Test2 ERP catalog','item_group':GROUP,'stock_uom':'Nos'},
        'content':{'item':SKU,'public_title':'Synthetic Test2 ERP catalog','full_description':'<p>Authoritative ERP synthetic description.</p>',
            'short_description':'Synthetic ERP catalog proof','seo_title':'Synthetic ERP SEO title','seo_description':'Synthetic ERP SEO description',
            'source_key':SOURCE,'source_payload':'{"fixture":"test2-erp-catalog-v1"}'},
        'mapping':{'item':SKU,'provider':'woocommerce','site_key':'synthetic-test2','external_product_id':'erp-fixture-v1','external_sku':SKU},
        'price':{'price_list':PRICE_LIST,'currency':'USD','item_price_rate':'12.50'}}
    candidate_source=None
    if candidate_api is not None:
        candidate_source=candidate_api.read_text()
        if not candidate_sha256 or hashlib.sha256(candidate_api.read_bytes()).hexdigest()!=candidate_sha256:
            raise ValueError('Reviewed candidate API hash required')
    elif candidate_sha256 is not None:raise ValueError('Candidate source required')
    setup={'candidate_api':candidate_source,'site':resolved['erp'].split('://')[1],'group':GROUP,'price_list':PRICE_LIST,'payload':payload}
    code='''import sys,json,frappe
from rootedops_commerce.api import import_product,catalog
a=json.load(sys.stdin);frappe.init(site=a['site']);frappe.connect();frappe.set_user('Administrator')
if a.get('candidate_api'):
 namespace={'__name__':'rootedops_commerce_candidate_api'}
 exec(compile(a['candidate_api'],'reviewed_candidate_api.py','exec'),namespace)
 import_product,catalog=namespace['import_product'],namespace['catalog']
try:
 assert frappe.conf.get('maintenance_mode') and frappe.conf.get('pause_scheduler')
 assert frappe.db.count('Email Account',{'enable_outgoing':1})==0
 assert frappe.db.count('Webhook',{'enabled':1})==0
 assert frappe.db.count('Notification',{'enabled':1})==0
 if not frappe.db.exists('Item Group',a['group']):
  frappe.get_doc({'doctype':'Item Group','item_group_name':a['group'],'parent_item_group':'All Item Groups','is_group':0}).insert()
 if not frappe.db.exists('Price List',a['price_list']):
  frappe.get_doc({'doctype':'Price List','price_list_name':a['price_list'],'currency':'USD','selling':1,'enabled':1}).insert()
 first=import_product(a['payload']);second=import_product(a['payload']);assert first==second
 result=catalog(a['payload']['item']['item_code'],a['price_list'])
 assert result['content']['publication_status']=='Draft'
 assert len(result['prices'])==1 and float(result['prices'][0]['item_price_rate'])==12.5
 assert frappe.db.count('Item',{'item_code':first['item']})==1
 assert frappe.db.count('Commerce Channel Mapping',{'name':first['mapping']})==1
 assert result['mappings'][0]['sync_enabled']==0
 frappe.db.commit();print(json.dumps(result,default=str))
except Exception:
 frappe.db.rollback();raise
finally:frappe.destroy()
'''
    process=subprocess.run(['docker','exec','-i','-w','/home/frappe/frappe-bench/sites','rootedops-full-test-erpnext-backend-1',
        '/home/frappe/frappe-bench/env/bin/python','-c',code],input=json.dumps(setup),text=True,capture_output=True)
    if process.returncode:
        log=private/'erp-catalog-fixture-failure.log';log.write_text(process.stdout+process.stderr);log.chmod(0o600)
        raise RuntimeError('Native ERP fixture failed; inspect private diagnostics; do not restore/reset')
    catalog=json.loads(process.stdout);private_write(private/'erp-native-catalog-fixture.json',catalog)
    credentials=json.loads((private/'wordpress-credentials.json').read_text())
    auth='Basic '+base64.b64encode((credentials['username']+':'+credentials['application_password']).encode()).decode()
    shop=resolved['shop']
    categories=api(shop+'/wp-json/wc/v3/products/categories?slug=erp-native-fixture',auth)
    category=categories[0] if categories else api(shop+'/wp-json/wc/v3/products/categories',auth,'POST',{'name':'ERP synthetic fixture','slug':'erp-native-fixture'})
    fixture=copy.deepcopy(catalog);fixture['content']['publication_status']='Published'
    inventory={'ecommerce_id':1,'erp_item_code':SKU,'desired_quantity':2}
    reviewed={'item':SKU,'provider':'woocommerce','site_key':'synthetic-test2','external_sku':SKU,
        'commercial':{'item_group':GROUP,'currency':'USD','price_list':PRICE_LIST,'woocommerce_category_ids':[category['id']],
            'erp_item_tax_template':None,'reviewed_no_item_tax':True,'woocommerce_tax_status':'none',
            'woocommerce_tax_class':'','woocommerce_media_ids':{}}}
    record=prepare(inventory,fixture,reviewed)
    one=upsert_draft(shop,auth,record);two=upsert_draft(shop,auth,record)
    assert one['id']==two['id'];verify_product(two,record,2)
    assert Decimal(two['regular_price'])==Decimal('12.50') and two['tax_status']=='none'
    report={'synthetic_only':True,'sku':SKU,'product_id':two['id'],'erp_item_price':'12.50','erp_service_layer_import_and_read':True,
        'erp_http_auth_tested':False,'candidate_api_sha256':candidate_sha256,
        'installed_application_upgrade_tested':False,'canonical_content_status':'Draft','channel_mapping_sync_enabled':False,
        'approval_fixture_only':True,'quantity_fixture_only':True,'mp_inventory_tested':False,
        'woocommerce_draft_idempotent':True,'financial_documents_created':False,'checkout_tested':False}
    private_write(private/'erp-woo-native-fixture-report.json',report);print(json.dumps(report))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('environment',type=Path)
    p.add_argument('--candidate-api',type=Path,help='Explicit native service-layer preview; does not replace installed app')
    p.add_argument('--candidate-api-sha256')
    a=p.parse_args();run(a.environment,a.candidate_api,a.candidate_api_sha256)
