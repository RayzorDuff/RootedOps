#!/usr/bin/env python3
"""Rehearse draft WooCommerce REST upserts using private ERP/MP test snapshots.

This uses an IN-MEMORY content approval fixture and omits remote image transfer.
Canonical ERP content stays Draft. It is not publication or checkout acceptance.
"""
import argparse
import base64
import copy
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'integrations/commerce'))
sys.path.insert(0,str(ROOT/'scripts'))
from commerce_restore import read_env
from ecwid_migrate import api, private_write
from channel import upsert_draft
from sync import prepare


def run(environment):
    environment=environment.resolve()
    if read_env(environment/'.env').get('ERPNEXT_SITE_NAME')!='erp-test.danks.store':
        raise ValueError('Only the authorized test environment is supported')
    private=environment/'private'
    rows=json.loads((private/'native-inventory.json').read_text())
    catalogs=json.loads((private/'erp-test-catalogs.json').read_text())
    credentials=json.loads((private/'wordpress-credentials.json').read_text())
    token=base64.b64encode((credentials['username']+':'+credentials['application_password']).encode()).decode()
    authorization='Basic '+token
    shop='https://shop-test.danks.store'
    source_hash=hashlib.sha256((private/'native-inventory.json').read_bytes()).hexdigest()
    results=[]
    for source in rows:
        row=dict(source)
        code=row['external_sku']
        if not code or code not in catalogs:
            raise ValueError('Missing exact-SKU ERP content match')
        catalog=copy.deepcopy(catalogs[code])
        if catalog['content']['item']!=code:
            raise ValueError('ERP identity mismatch')
        # Explicit test fixture only: canonical ERP approval is not changed.
        catalog['content']['publication_status']='Published'
        catalog['content']['gallery']=[]
        row['erp_item_code']=code
        reviewed={'item':code,'provider':'woocommerce','site_key':'shop-test','external_sku':code}
        record=prepare(row,catalog,reviewed)
        product=upsert_draft(shop,authorization,record)
        repeated=upsert_draft(shop,authorization,record)
        assert product['id']==repeated['id']
        assert repeated['status']=='draft'
        assert repeated['stock_quantity']==int(row['desired_quantity'])
        assert repeated['name']==record['woocommerce']['name']
        if record['woocommerce']['description'].strip():
            assert repeated['description'].strip()
        results.append({'ecommerce_id':row['ecommerce_id'],'item':code,'product_id':product['id'],
                        'quantity':repeated['stock_quantity']})
        if len(results)==1:
            endpoint=shop+'/wp-json/wc/v3/products/'+str(product['id'])
            original=record['woocommerce']['meta_data']
            api(endpoint,authorization,'PUT',{'meta_data':[{'key':'_rootedops_source_key','value':'unowned-test-fixture'}]})
            try:
                try:upsert_draft(shop,authorization,record)
                except ValueError:pass
                else:raise AssertionError('Unowned target was overwritten')
            finally:
                api(endpoint,authorization,'PUT',{'meta_data':original})
            # A storefront-side quantity change must be overwritten by MP's value.
            api(endpoint,authorization,'PUT',{'stock_quantity':int(row['desired_quantity'])+17})
            corrected=upsert_draft(shop,authorization,record)
            assert corrected['stock_quantity']==int(row['desired_quantity'])
    assert len({r['product_id'] for r in results})==len(rows)
    assert hashlib.sha256((private/'native-inventory.json').read_bytes()).hexdigest()==source_hash
    private_write(private/'live-sync-products.json',results)
    report={'draft_products_verified':len(results),'idempotent_retries':len(results),
            'unowned_target_refused':True,'mp_quantity_reapplied':True,
            'canonical_erp_content_changed':False,'mp_snapshot_changed':False,
            'approval_fixture_only':True,'remote_images_transferred':False,'checkout_tested':False}
    private_write(private/'live-sync-report.json',report)
    print(json.dumps(report))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('environment',type=Path)
    run(p.parse_args().environment)
