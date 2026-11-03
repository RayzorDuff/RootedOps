#!/usr/bin/env python3
"""Read-only installed readiness for a reviewed Ecwid pilot product batch.

No Woo API credentials, test2 hostnames, database mutations, stock changes or
payment operations. It checks exact source identities and installed media.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from commerce_production_staging_batch import compiled_guard
from commerce_catalog_batch import records_for_batch
from commerce_production_media import guard_live

ERP = r"""
import json,sys,frappe,rootedops_commerce
input=json.load(sys.stdin)
frappe.init(site='erp.danks.store');frappe.connect()
try:
 assert frappe.local.site=='erp.danks.store'
 assert rootedops_commerce.__version__=='0.3.1'
 pl=frappe.get_doc('Price List','Standard Selling')
 assert pl.currency=='USD' and pl.selling and pl.enabled
 assert frappe.db.exists('Item Group','Products')
 assert frappe.db.exists('UOM','Nos')
 counts={dt:frappe.db.count(dt) for dt in
         ('Item','Commercial Product Content','Commerce Channel Mapping',
          'Item Price','Sales Order','Sales Invoice','Payment Entry','Stock Entry','Bin','File')}
 result=[]
 for record in input['records']:
  code=record['item']['item_code']
  # Existing target Items require a separate ownership/reconciliation review.
  for dt in ('Item','Commercial Product Content'):
   if frappe.db.exists(dt,code):
    raise ValueError('Existing ERP identity requires explicit reconciliation: '+dt+' '+code)
  if frappe.db.exists('Item Price',{'item_code':code,'price_list':'Standard Selling'}):
   raise ValueError('Existing ERP price requires explicit review: '+code)
  external=record['mapping']['external_product_id']
  if frappe.db.exists('Commerce Channel Mapping',{'provider':'ecwid',
      'site_key':'95802503','external_product_id':external}):
   raise ValueError('Existing ERP source mapping requires review: '+external)
  for img in record['content']['gallery']:
   assert img['image'].startswith('/files/')
   assert frappe.db.exists('File',{'file_url':img['image'],'is_private':0}), img['image']
  result.append({'item':code,'gallery':len(record['content']['gallery']),'available':True})
 print(json.dumps({'site':frappe.local.site,'app_version':rootedops_commerce.__version__,
                   'counts':counts,'records':result}))
finally:
 frappe.db.rollback()
 frappe.destroy()
"""

WP = r"""
require '/var/www/html/wp-load.php';
$input=json_decode(stream_get_contents(STDIN),true,512,JSON_THROW_ON_ERROR);
if (!class_exists('WooCommerce') ||
    get_option('siteurl')!=='https://shop-test.danks.store' ||
    get_option('woocommerce_coming_soon')!=='yes' ||
    get_option('woocommerce_calc_taxes')!=='no' ||
    (int)wp_count_posts('product')->publish!==0 ||
    count(WC()->payment_gateways()->get_available_payment_gateways())!==0 ||
    count(get_posts(['post_type'=>'shop_webhook','post_status'=>'publish','numberposts'=>1]))!==0) {
 throw new Exception('Staging shop safety drift');
}
if (get_woocommerce_currency()!=='USD') throw new Exception('Store currency drift');
$categories=['16'=>'Gourmet Mushrooms','17'=>'Miscellaneous',
             '18'=>'Grow Kits and Mycology Supplies'];
foreach ($categories as $id=>$name) {
 $term=get_term((int)$id,'product_cat');
 if (!$term || is_wp_error($term) || $term->name!==$name)
  throw new Exception('Reviewed category drift: '.$id);
}
$rows=[];
foreach ($input['records'] as $record) {
 $sku=$record['woocommerce']['sku'];
 if (wc_get_product_id_by_sku($sku))
  throw new Exception('Existing destination SKU requires review: '.$sku);
 foreach ($record['woocommerce']['images'] as $image) {
  $id=(int)$image['id'];
  if (!wp_attachment_is_image($id)) throw new Exception('Missing image ID: '.$id);
  $path=get_attached_file($id);
  if (!$path || !is_file($path) || !get_post_meta($id,'_rootedops_media_sha256',true))
   throw new Exception('Unverified source media attachment: '.$id);
 }
 $rows[]=['sku'=>$sku,'media'=>count($record['woocommerce']['images']),
          'destination_absent'=>true];
}
echo json_encode(['site'=>get_option('siteurl'),
                 'drafts'=>(int)wp_count_posts('product')->draft,
                 'published'=>(int)wp_count_posts('product')->publish,
                 'records'=>$rows],JSON_THROW_ON_ERROR);
"""

def run_native(argv,payload):
    result=subprocess.run(argv,input=json.dumps(payload),capture_output=True,text=True)
    if result.returncode:
        raise RuntimeError("Read-only installed preflight failed: "+result.stderr[-1500:])
    return json.loads(result.stdout)

def inspect(document, deployment):
    if not (deployment/".env").is_file() or not (deployment/"docker/docker-compose.yml").is_file():
        raise ValueError("Installed RootedOps checkout required")
    guard_live(deployment)
    records=records_for_batch(document)
    if any(r.get('parent_sku') or r['item'].get('has_variants') for r in records):
        raise ValueError("Simple pilot products only")
    if any(r['price']['price_list']!='Standard Selling' for r in records):
        raise ValueError("Unexpected price list")
    erp=run_native(['docker','compose','--env-file',str(deployment/'.env'),
        '-f',str(deployment/'docker/docker-compose.yml'),'exec','-T','-w',
        '/home/frappe/frappe-bench/sites','erpnext-backend',
        '/home/frappe/frappe-bench/env/bin/python','-c',ERP],{'records':records})
    woo=run_native(['docker','exec','-i','dank-store-test-dank-wordpress-1',
                    'php','-r',WP],{'records':records})
    if len(erp['records'])!=len(records) or len(woo['records'])!=len(records):
        raise ValueError('Read-back count mismatch')
    return {'erp':erp,'woo':woo,'ready_for_review':True,'writes':False}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo-root',type=Path,required=True)
    p.add_argument('--compiled',type=Path,required=True)
    p.add_argument('--sha256',required=True)
    a=p.parse_args()
    if compiled_guard(a.compiled)!=a.sha256:
        raise ValueError('Compiled SHA256 mismatch')
    result=inspect(json.loads(a.compiled.read_text()),a.repo_root.resolve())
    result['compiled_sha256']=a.sha256
    print(json.dumps(result,indent=2))

if __name__=='__main__':
    main()
