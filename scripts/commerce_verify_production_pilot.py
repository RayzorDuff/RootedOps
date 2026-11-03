#!/usr/bin/env python3
"""Independent read-only reconciliation of installed ERP and staging Woo pilot.

Checks immutable compiled batch and private recovery receipt. No writes. Does
not use test2 runner and rejects any missing or changed source identity.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from commerce_production_draft_import import verify_compiled
from commerce_production_batch_readiness import run_native
from commerce_production_media import guard_live

ERP_READ = r"""
import sys,json,frappe,rootedops_commerce
from decimal import Decimal
from rootedops_commerce.api import catalog
a=json.load(sys.stdin)
frappe.init(site='erp.danks.store');frappe.connect();frappe.set_user('Administrator')
try:
 assert rootedops_commerce.__version__=='0.3.1'
 before={d:frappe.db.count(d) for d in ('Sales Order','Sales Invoice',
   'Payment Entry','Stock Entry','Bin','File')}
 out=[]
 for r in a['records']:
  code=r['item']['item_code']
  item=frappe.get_doc('Item',code)
  assert item.item_group==r['item']['item_group'],code
  assert item.stock_uom==r['item']['stock_uom'],code
  assert not item.is_stock_item,code
  actual=catalog(code,'Standard Selling')
  content=actual['content']
  assert content['publication_status']=='Draft'
  assert content['source_key']==r['source_key']
  assert content['source_payload']==r['content']['source_payload']
  for field in ('public_title','full_description','short_description','seo_title','seo_description'):
   assert (content.get(field) or '')==(r['content'].get(field) or ''),(code,field)
  assert [(x['image'],x['source_url']) for x in content['gallery']]==[
    (x['image'],x['source_url']) for x in r['content']['gallery']]
  assert len(actual['prices'])==1,code
  price=actual['prices'][0]
  assert price['price_list']=='Standard Selling' and price['currency']=='USD'
  assert Decimal(str(price['item_price_rate']))==Decimal(str(r['price']['item_price_rate']))
  assert len(actual['mappings'])==1,code
  mapping=actual['mappings'][0]
  assert mapping['provider']=='ecwid' and mapping['site_key']=='95802503'
  assert mapping['external_product_id']==r['mapping']['external_product_id']
  assert mapping['external_sku']==r['mapping']['external_sku']
  assert not mapping['sync_enabled']
  for img in content['gallery']:
   assert frappe.db.exists('File',{'file_url':img['image'],'is_private':0})
  out.append({'item_code':code,'verified':True,
              'media':len(content['gallery'])})
 assert before=={d:frappe.db.count(d) for d in before}
 print(json.dumps({'site':frappe.local.site,'records':out,
                   'counts':{d:frappe.db.count(d) for d in
                   ('Item','Commercial Product Content','Commerce Channel Mapping','Item Price',
                    'Sales Order','Sales Invoice','Payment Entry','Stock Entry','Bin','File')}}))
finally:
 frappe.db.rollback();frappe.destroy()
"""

WOO_READ = r"""
require '/var/www/html/wp-load.php';
$a=json_decode(stream_get_contents(STDIN),true,512,JSON_THROW_ON_ERROR);
if (!class_exists('WooCommerce') ||
    get_option('siteurl')!=='https://shop-test.danks.store' ||
    get_option('woocommerce_coming_soon')!=='yes' ||
    get_option('woocommerce_calc_taxes')!=='no' ||
    get_woocommerce_currency()!=='USD' ||
    (int)wp_count_posts('product')->publish!==0 ||
    count(WC()->payment_gateways()->get_available_payment_gateways())!==0 ||
    count(get_posts(['post_type'=>'shop_webhook','post_status'=>'publish','numberposts'=>1]))!==0)
 throw new Exception('Staging safety drift');
$out=[];
foreach ($a['records'] as $r) {
 $expected=$r['woocommerce'];$sku=$expected['sku'];
 $id=wc_get_product_id_by_sku($sku);
 if (!$id) throw new Exception('Missing SKU: '.$sku);
 $product=wc_get_product($id);
 if (!$product || !$product->is_type('simple') ||
     $product->get_sku()!==$sku ||
     $product->get_status()!=='draft' ||
     $product->get_catalog_visibility()!=='hidden' ||
     !$product->get_manage_stock() ||
     (int)$product->get_stock_quantity()!==0 ||
     $product->get_stock_status()!=='outofstock' ||
     $product->get_backorders()!=='no' ||
     $product->get_tax_status()!=='none' ||
     $product->get_name()!==$expected['name'] ||
     $product->get_description()!==$expected['description'] ||
     $product->get_short_description()!==$expected['short_description'] ||
     wc_format_decimal($product->get_regular_price())!==wc_format_decimal($expected['regular_price']))
  throw new Exception('Product field drift: '.$sku);
 $cats=array_map('intval',$product->get_category_ids());sort($cats);
 $wanted=array_map(fn($x)=>(int)$x['id'],$expected['categories']);sort($wanted);
 if ($cats!==$wanted) throw new Exception('Categories drift: '.$sku);
 $media=array_values(array_filter(array_merge(
    [$product->get_image_id()],$product->get_gallery_image_ids())));
 $wanted_media=array_map(fn($x)=>(int)$x['id'],$expected['images']);
 if (array_map('intval',$media)!==$wanted_media)
  throw new Exception('Gallery drift: '.$sku);
 foreach ($expected['meta_data'] as $m)
  if ($product->get_meta($m['key'],true)!=$m['value'])
   throw new Exception('Provenance drift: '.$sku.' '.$m['key']);
 foreach ($media as $attachment) {
  $file=get_attached_file($attachment);
  $sha=get_post_meta($attachment,'_rootedops_media_sha256',true);
  if (!is_file($file) || !preg_match('/^[a-f0-9]{64}$/D',$sha) ||
      hash_file('sha256',$file)!==$sha)
   throw new Exception('Media checksum drift: '.$sku);
 }
 $matches=wc_get_products(['sku'=>$sku,'limit'=>-1,'return'=>'ids']);
 if (count($matches)!==1 || (int)$matches[0]!==$id)
  throw new Exception('Duplicate SKU: '.$sku);
 $out[]=['source_key'=>$r['source_key'],'sku'=>$sku,
         'woocommerce_id'=>(int)$id,'media_ids'=>array_map('intval',$media),
         'status'=>'draft','verified'=>true];
}
echo json_encode(['site'=>get_option('siteurl'),'records'=>$out,
  'drafts'=>(int)wp_count_posts('product')->draft,
  'published'=>(int)wp_count_posts('product')->publish],JSON_THROW_ON_ERROR);
"""

def reconcile(deployment,compiled,sha,receipt):
    records=verify_compiled(compiled,sha)
    if not receipt.is_file():
        raise ValueError("Import receipt required")
    saved=json.loads(receipt.read_text())
    if (saved.get("compiled_sha256")!=sha or
        saved.get("scope")!="erp.danks.store|shop-test.danks.store" or
        saved.get("erp_committed") is not True):
        raise ValueError("Import receipt scope/status drift")
    if not isinstance(saved.get("products"),dict) or len(saved["products"])!=5:
        raise ValueError("Exactly five receipted Woo products required")
    guard_live(deployment)
    erp=run_native(['docker','compose','--env-file',str(deployment/'.env'),
       '-f',str(deployment/'docker/docker-compose.yml'),'exec','-T','-w',
       '/home/frappe/frappe-bench/sites','erpnext-backend',
       '/home/frappe/frappe-bench/env/bin/python','-c',ERP_READ],{'records':records})
    woo=run_native(['docker','exec','-i','dank-store-test-dank-wordpress-1',
       'php','-r',WOO_READ],{'records':records})
    if len(erp['records'])!=5 or len(woo['records'])!=5:
        raise ValueError("Read-back record counts differ")
    by_key={p['source_key']:p for p in woo['records']}
    if set(by_key)!=set(saved['products']):
        raise ValueError("Receipt source-key discrepancy")
    for key,record in by_key.items():
        previous=saved['products'][key]
        for field in ('source_key','sku','woocommerce_id','media_ids'):
            if record[field]!=previous[field]:
                raise ValueError("Woo receipt drift: "+field)
    counts=erp["counts"]
    if any(counts[d]!=5 for d in ('Item','Commercial Product Content',
                                  'Commerce Channel Mapping','Item Price')):
        raise ValueError("Unexpected first-cohort ERP counts")
    if any(counts[d]!=0 for d in ('Sales Order','Sales Invoice',
                                  'Payment Entry','Stock Entry','Bin')):
        raise ValueError("Unexpected financial or stock records")
    if woo['published']!=0 or woo['drafts']!=5:
        raise ValueError("Unexpected WooCommerce product counts")
    return {"compiled_sha256":sha,"erp_items":5,"woo_drafts":5,
            "woocommerce_published":0,"erp":erp,"woo":woo,
            "receipt_matches":True,"reconciliation":"PASSED","writes":False}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo-root",type=Path,required=True)
    p.add_argument("--compiled",type=Path,required=True)
    p.add_argument("--sha256",required=True)
    p.add_argument("--receipt",type=Path,required=True)
    a=p.parse_args()
    result=reconcile(a.repo_root.resolve(),a.compiled,a.sha256,a.receipt)
    print(json.dumps(result,indent=2))

if __name__=="__main__":
    main()
