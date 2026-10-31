#!/usr/bin/env python3
"""Synthetic draft catalog REST proof, not restored-catalog or checkout acceptance."""
import base64
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/commerce'))
from ecwid_migrate import api
from channel import upsert_draft
from commerce_live_sync_smoke import verify_product


def run(environment):
    environment=environment.resolve()
    if (environment/'TEST_ENVIRONMENT').read_text().strip()!='rootedops-full-test':
        raise ValueError('Explicit isolated environment required')
    private=environment/'private'
    installed=json.loads((private/'wordpress-offline-receipt.json').read_text())
    if installed['controls']!={'cron_disabled':True,'http_blocked':True,'mail_blocked':True,'payment_gateways':0}:
        raise ValueError('Isolated shop receipt required')
    c=json.loads((private/'wordpress-credentials.json').read_text())
    auth='Basic '+base64.b64encode((c['username']+':'+c['application_password']).encode()).decode()
    root='https://shop-test.danks.store'
    category=api(root+'/wp-json/wc/v3/products/categories?slug=rootedops-synthetic',auth)
    category=category[0] if category else api(root+'/wp-json/wc/v3/products/categories',auth,'POST',{'name':'RootedOps synthetic','slug':'rootedops-synthetic'})
    def record(suffix,quantity=2):
        sku='SYN-ROOTEDOPS-'+suffix
        return {'source_key':'synthetic:staging:'+suffix,'expected_currency':'USD','item':{},'woocommerce':{
            'sku':sku,'name':'Synthetic staging '+suffix,'status':'draft','regular_price':'12.50',
            'description':'<p>Synthetic catalog fixture. Not for sale.</p>','short_description':'Synthetic fixture',
            'manage_stock':True,'stock_quantity':quantity,'tax_status':'none','tax_class':'',
            'categories':[{'id':category['id']}],
            'meta_data':[{'key':'_rootedops_source_key','value':'synthetic:staging:'+suffix},
                         {'key':'_rootedops_erp_item','value':sku},
                         {'key':'_rootedops_seo_title','value':'Synthetic staging fixture'},
                         {'key':'_rootedops_seo_description','value':'Synthetic SEO verification only'}]}}
    simple=record('SIMPLE');one=upsert_draft(root,auth,simple);two=upsert_draft(root,auth,simple)
    assert one['id']==two['id'];verify_product(two,simple,2)
    assert two['regular_price']=='12.50' and two['tax_status']=='none' and category['id'] in [c['id'] for c in two['categories']]
    attrs=[{'name':'Size','visible':True,'variation':True,'options':['Small','Large']}]
    parent=record('VARIABLE');parent['item']={'has_variants':True};parent['woocommerce'].update(manage_stock=False,stock_quantity=None)
    p=upsert_draft(root,auth,parent,attributes=attrs)
    assert p['type']=='variable' and p['status']=='draft'
    variants=[]
    for size in ['Small','Large']:
        child=record(size.upper());child['item']={'parent_sku':parent['woocommerce']['sku']}
        a=upsert_draft(root,auth,child,parent_id=p['id'],attributes=[{'name':'Size','option':size}])
        b=upsert_draft(root,auth,child,parent_id=p['id'],attributes=[{'name':'Size','option':size}])
        assert a['id']==b['id'] and b['sku']==child['woocommerce']['sku'] and b['stock_quantity']==2 and b['regular_price']=='12.50'
        variants.append(b['id'])
    api(root+'/wp-json/wc/v3/products/'+str(one['id']),auth,'PUT',{'stock_quantity':19})
    assert upsert_draft(root,auth,simple)['stock_quantity']==2
    bad=record('SIMPLE');bad['source_key']='synthetic:unowned';bad['woocommerce']['meta_data'][0]['value']='synthetic:unowned'
    try:upsert_draft(root,auth,bad)
    except ValueError:pass
    else:raise AssertionError('Unowned product overwrite was accepted')
    report={'fixture_only':True,'simple_id':one['id'],'parent_id':p['id'],'variation_ids':variants,
            'draft_only':True,'idempotent_upserts':True,'stock_drift_corrected':True,'ownership_refusal':True,
            'price_category_tax_and_seo_metadata_verified':True,'restored_erp_or_mp_changed':False,
            'media_transferred':False,'seo_rendering_tested':False,'checkout_tested':False}
    path=private/'woo-native-smoke.json';path.write_text(json.dumps(report,indent=2));path.chmod(0o600)
    print(json.dumps(report))

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('environment',type=Path)
    run(p.parse_args().environment)
