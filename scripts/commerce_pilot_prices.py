#!/usr/bin/env python3
"""Reconcile the three existing real Ecwid pilot prices on isolated test2.

Read-only by default; --apply enables additive ERP Item Prices and draft Woo prices.
Uses existing installed ERP import and Woo channel adapters. No catalog recreation.
"""
import argparse
import base64
from decimal import Decimal
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'integrations/commerce'))
from ecwid_migrate import api,private_write
from channel import upsert_draft
from staging_origin import staging_pair

EXPECTED={'610274980':('M5P9B1D6Q8R2S','14.95'),
          '610274742':('cdbd6f64-2637-488c-b9fc-0a5a47bb7322','9.95'),
          '711334880':('E3ZY47P9K64TT','9.95')}
PRICE_LIST='Ecwid Catalog Pilot USD'


def pilot_records(plan):
    if plan.get('errors') or len(plan['products'])!=3:
        raise ValueError('Exact error-free three-product pilot required')
    seen=set()
    for row in plan['products']:
        identity=row['mapping']['external_product_id']
        if identity in seen or identity not in EXPECTED:
            raise ValueError('Pilot source identity drift')
        seen.add(identity);sku,rate=EXPECTED[identity]
        if (row['content']['item']!=sku or row['mapping']['external_sku']!=sku
            or row['mapping']['provider']!='ecwid' or row['mapping']['site_key']!='95802503'
            or row['source_key']!='ecwid:95802503:product:'+identity
            or Decimal(str(row['price']))!=Decimal(rate)
            or row['item'].get('has_variants') or row['item'].get('parent_sku')):
            raise ValueError('Pilot SKU/source/rate/type drift')
    return plan['products']


NATIVE='''import sys,json,frappe,rootedops_commerce
from decimal import Decimal
from rootedops_commerce.api import import_product,catalog
a=json.load(sys.stdin);frappe.init(site='erp-test2.danks.store');frappe.connect();frappe.set_user('Administrator')
try:
 assert rootedops_commerce.__version__=='0.3.1'
 assert frappe.conf.get('maintenance_mode') and frappe.conf.get('pause_scheduler')
 for dt,f in [('Email Account',{'enable_outgoing':1}),('Webhook',{'enabled':1}),('Notification',{'enabled':1})]:assert frappe.db.count(dt,f)==0
 before={dt:frappe.db.count(dt) for dt in ['Item','Sales Order','Sales Invoice','Payment Entry']}
 # Validate every existing source/content before creating even a Price List.
 for r in a['records']:
  content=frappe.get_doc('Commercial Product Content',r['content']['item'])
  assert content.source_key==r['source_key'] and content.source_payload==r['content']['source_payload']
  assert content.publication_status=='Draft'
  item=frappe.get_doc('Item',r['content']['item']);assert not item.has_variants and not item.variant_of
  maps=frappe.get_all('Commerce Channel Mapping',filters={'item':item.name},fields=['sync_enabled'])
  assert maps and all(not m.sync_enabled for m in maps)
 if a['apply'] and not frappe.db.exists('Price List',a['price_list']):
  frappe.get_doc({'doctype':'Price List','price_list_name':a['price_list'],'currency':'USD','selling':1,'enabled':1}).insert()
 out=[]
 for r in a['records']:
  sku=r['content']['item'];item=frappe.get_doc('Item',sku)
  if a['apply']:
   payload={'item':{'item_code':sku,'item_name':item.item_name,'item_group':item.item_group,'stock_uom':item.stock_uom},'content':r['content'],'mapping':r['mapping'],
    'price':{'price_list':a['price_list'],'currency':'USD','item_price_rate':r['price']}}
   assert import_product(payload)==import_product(payload)
  prices=catalog(sku,a['price_list'])['prices']
  assert len(prices)<=1
  if prices:assert Decimal(str(prices[0]['item_price_rate']))==Decimal(str(r['price']))
  if a['apply']:assert len(prices)==1
  out.append({'sku':sku,'price_id':prices[0]['name'] if prices else None,'rate':str(prices[0]['item_price_rate']) if prices else None})
 assert before=={dt:frappe.db.count(dt) for dt in before}
 if a['apply']:frappe.db.commit()
 else:frappe.db.rollback()
 print(json.dumps(out))
except Exception:frappe.db.rollback();raise
finally:frappe.destroy()
'''


def run(environment,apply=False):
    from commerce_staging_targets import targets
    if os.geteuid()!=0:raise ValueError('Run through existing sudo authorization')
    env=environment.resolve();target=targets(env)
    erp,shop=staging_pair(target['erp'],target['shop'])
    if erp!='https://erp-test2.danks.store' or shop!='https://shop-test2.danks.store':
        raise ValueError('Existing test2 pilot only')
    private=env/'private';pilot=private/'ecwid-pilot'
    if json.loads((private/'wordpress-offline-receipt.json').read_text())['controls']!={'cron_disabled':True,'http_blocked':True,'mail_blocked':True,'payment_gateways':0}:
        raise ValueError('Offline shop receipt required')
    # Read only expected isolated containers. Never start/recreate services here.
    for name,project in [('rootedops-full-test-erpnext-backend-1','rootedops-full-test'),('dank-store-test-dank-wordpress-1','dank-store-test')]:
        c=json.loads(subprocess.check_output(['docker','inspect',name]))[0]
        if c['Config']['Labels'].get('com.docker.compose.project')!=project or not c['State']['Running'] or any((c['NetworkSettings']['Ports'] or {}).values()):
            raise ValueError('Isolated running container required')
        for network in c['NetworkSettings']['Networks']:
            if not json.loads(subprocess.check_output(['docker','network','inspect',network]))[0]['Internal']:
                raise ValueError('Internal networking required')
    records=pilot_records(json.loads((pilot/'plan.json').read_text()))
    credentials=json.loads((private/'wordpress-credentials.json').read_text())
    auth='Basic '+base64.b64encode((credentials['username']+':'+credentials['application_password']).encode()).decode()
    # Woo ownership and currency preflight happens before ERP writes.
    if api(shop+'/wp-json/wc/v3/settings/general/woocommerce_currency',auth)['value']!='USD':raise ValueError('Woo currency drift')
    from urllib.parse import urlencode
    old={}
    for r in records:
        # PUT returns edit-context content. GET view context applies WordPress
        # paragraph formatting and cannot be compared byte-for-byte with it.
        sku=r['content']['item'];matches=api(shop+'/wp-json/wc/v3/products?'+urlencode({'sku':sku,'context':'edit'}),auth)
        if len(matches)!=1:raise ValueError('Exact existing Woo pilot required')
        product=matches[0];meta={m['key']:m['value'] for m in product['meta_data']}
        if (product['sku']!=sku or product['status']!='draft' or product['type']!='simple' or product['catalog_visibility']!='hidden'
            or product['stock_quantity']!=0 or not product['manage_stock'] or meta.get('_rootedops_source_key')!=r['source_key']):
            raise ValueError('Woo pilot identity/isolation drift')
        old[sku]=product
    args={'records':records,'price_list':PRICE_LIST,'apply':apply}
    native=subprocess.run(['docker','exec','-i','-w','/home/frappe/frappe-bench/sites','rootedops-full-test-erpnext-backend-1','/home/frappe/frappe-bench/env/bin/python','-c',NATIVE],input=json.dumps(args),text=True,capture_output=True)
    if native.returncode:
        private_write(pilot/'price-error.json',{'stdout':native.stdout,'stderr':native.stderr})
        raise RuntimeError('ERP price validation failed; private diagnostics saved')
    result=[]
    for r in records:
        sku=r['content']['item'];product=old[sku]
        if apply:
            projection={'source_key':r['source_key'],'item':{},'expected_currency':'USD',
                        'woocommerce':{'sku':sku,'status':'draft','regular_price':str(r['price'])}}
            one=upsert_draft(shop,auth,projection);product=upsert_draft(shop,auth,projection)
            assert one['id']==product['id']==old[sku]['id']
            assert Decimal(product['regular_price'])==Decimal(str(r['price']))
            for field in ['status','catalog_visibility','stock_quantity','manage_stock','description','short_description','images','categories']:
                assert product[field]==old[sku][field],field
        result.append({'sku':sku,'woo_id':product['id'],'woo_price':product['regular_price'],'expected_rate':str(r['price'])})
    report={'applied':apply,'currency':'USD','currency_evidence':'user confirmed USD','erp':json.loads(native.stdout),'woocommerce':result,
            'taxes_verified':False,'variations_verified':False,'publication_changed':False,'inventory_changed':False}
    private_write(pilot/('prices-applied.json' if apply else 'prices-preflight.json'),report)
    print(json.dumps(report))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('environment',type=Path);parser.add_argument('--apply',action='store_true')
    args=parser.parse_args();run(args.environment,args.apply)
