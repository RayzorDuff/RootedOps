#!/usr/bin/env python3
"""Join reviewed MushroomProcess snapshots to ERP content and stage Woo drafts.

Dry-run by default. A reviewed mapping file supplies ERP identities, external
parent/variation attributes and channel settings. No inferred inventory identity.
"""
import argparse
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlencode, urlsplit

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'erpnext/apps/rootedops_commerce'))
from rootedops_commerce.contract import compose_projection
from ecwid_migrate import api, private_write
from channel import upsert_draft


def prepare(row, catalog, reviewed):
    content = catalog['content']
    if catalog['item']['disabled']:
        raise ValueError('Disabled ERP Item')
    if content['publication_status'] != 'Published':
        raise ValueError('ERP content must be approved Published before channel projection')
    mapping = dict(reviewed, mushroomprocess_ecommerce_id=str(row['ecommerce_id']))
    projection = compose_projection(content,mapping,row)
    c=projection['content']
    source_key = c.get('source_key') or 'erp:item:' + c['item']
    return {'source_key':source_key,
            'item':{'parent_sku':reviewed.get('parent_sku'), 'has_variants':reviewed.get('has_variants',False)},
            'woocommerce':{'sku':reviewed['external_sku'],'name':c['public_title'],'status':'draft',
                'description':c.get('full_description',''),'short_description':c.get('short_description',''),
                'images':[{'src':i['image']} for i in c.get('gallery',[])],
                'manage_stock':True,'stock_quantity':projection['quantity'],
                'meta_data':[{'key':'_rootedops_source_key','value':source_key},
                             {'key':'_rootedops_erp_item','value':c['item']},
                             {'key':'_rootedops_seo_title','value':c.get('seo_title','')},
                             {'key':'_rootedops_seo_description','value':c.get('seo_description','')}]}}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('snapshot',type=Path);p.add_argument('reviewed_map',type=Path);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--erp-url',default='https://erp-test.danks.store');p.add_argument('--shop-url',default='https://shop-test.danks.store')
    p.add_argument('--apply-staging',action='store_true');a=p.parse_args()
    if urlsplit(a.erp_url).hostname!='erp-test.danks.store' or urlsplit(a.shop_url).hostname!='shop-test.danks.store':
        p.error('Only authorized test hostnames are supported')
    rows=json.loads(a.snapshot.read_text());reviewed=json.loads(a.reviewed_map.read_text());results=[]
    for row in rows:
        m=reviewed.get(str(row['ecommerce_id']))
        if not m:raise ValueError('Missing reviewed mapping for ecommerce ID '+str(row['ecommerce_id']))
        if m['provider']!='woocommerce':raise ValueError('This adapter projects WooCommerce only')
        endpoint=a.erp_url.rstrip('/')+'/api/method/rootedops_commerce.api.catalog?'+urlencode({'item':m['item']})
        catalog=api(endpoint,os.environ['ERP_AUTHORIZATION'])['message']
        record=prepare(row,catalog,m)
        result={'ecommerce_id':row['ecommerce_id'],'record':record,'status':'planned'}
        if a.apply_staging:
            target=upsert_draft(a.shop_url,os.environ['WC_AUTHORIZATION'],record,
                                parent_id=m.get('parent_id'),attributes=m.get('attributes'))
            result.update(status='draft_upserted',external_product_id=target['id'])
        results.append(result)
    private_write(a.output,results)

if __name__=='__main__':main()
