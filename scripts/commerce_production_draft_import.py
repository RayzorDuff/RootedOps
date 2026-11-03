#!/usr/bin/env python3
"""Explicit, resumable five-product ERP production / Woo staging draft import.

This is a *product-only* native Docker import. It does not enable publication,
checkout, taxes, commerce sync, stock, order processing or payments. Run only
after the installed preflight and a restorable backup. Source and media must
already be reviewed and receipts preserved. Read-only unless --apply supplied.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
sys.path.insert(0,str(ROOT/"integrations/commerce"))
from ecwid_migrate import private_write
from commerce_catalog_batch import records_for_batch
from commerce_production_staging_batch import compiled_guard
from commerce_production_media import guard_live

FIRST_BATCH_SHA = "ed49bd43b49cb9f705bd780f5f8d2220bd7aec32b2e4cc17c7dbde1a53f389d6"
FIRST_BATCH_IDS = {"610274451","610274742","610274979","610274980","610276199"}

# All operations in this block are in one Frappe DB transaction. Native
# import_product handles allowed fields, permissions, pricing and idempotence.
ERP_SCRIPT = r"""
import json,sys,frappe,rootedops_commerce
from decimal import Decimal
from rootedops_commerce.api import import_product,catalog
a=json.load(sys.stdin)
frappe.init(site='erp.danks.store');frappe.connect();frappe.set_user('Administrator')
try:
 assert frappe.local.site=='erp.danks.store'
 assert rootedops_commerce.__version__=='0.3.1'
 pl=frappe.get_doc('Price List','Standard Selling')
 assert pl.enabled and pl.selling and pl.currency=='USD'
 before={dt:frappe.db.count(dt) for dt in
   ('Sales Order','Sales Invoice','Payment Entry','Stock Entry','Bin','File')}
 result=[]
 for r in a['records']:
  code=r['item']['item_code']
  assert r['mapping']['sync_enabled']==0
  assert r['mapping']['site_key']=='95802503'
  assert r['content']['publication_status']=='Draft'
  assert r['price']['currency']=='USD'
  assert r['price']['price_list']=='Standard Selling'
  for dt,value in [('Item Group',r['item']['item_group']),('UOM',r['item']['stock_uom'])]:
   assert frappe.db.exists(dt,value)
  for image in r['content']['gallery']:
   assert image['image'].startswith('/files/')
   assert frappe.db.exists('File',{'file_url':image['image'],'is_private':0})
  if frappe.db.exists('Item',code):
   doc=frappe.get_doc('Item',code)
   assert doc.is_stock_item==0,code
  payload={k:r[k] for k in ('item','content','mapping','price')}
  if a['apply']:
   first=import_product(payload)
   counts={dt:frappe.db.count(dt) for dt in
     ('Item','Commercial Product Content','Commerce Channel Mapping','Item Price')}
   assert import_product(payload)==first
   assert counts=={dt:frappe.db.count(dt) for dt in counts}
   actual=catalog(code,'Standard Selling')
   assert actual['item']['item_code']==code
   assert actual['item']['disabled'] in (0,None)
   assert actual['content']['publication_status']=='Draft'
   assert actual['content']['source_key']==r['source_key']
   assert actual['content']['source_payload']==r['content']['source_payload']
   for field in ('public_title','full_description','short_description',
                 'seo_title','seo_description'):
    assert (actual['content'].get(field) or '')==(r['content'].get(field) or ''),(code,field)
   assert [x['image'] for x in actual['content']['gallery']]==[x['image'] for x in r['content']['gallery']]
   assert [x['source_url'] for x in actual['content']['gallery']]==[x['source_url'] for x in r['content']['gallery']]
   assert len(actual['prices'])==1
   assert Decimal(str(actual['prices'][0]['item_price_rate']))==Decimal(str(r['price']['item_price_rate']))
   assert len(actual['mappings'])==1 and not actual['mappings'][0]['sync_enabled']
   assert actual['mappings'][0]['external_product_id']==r['mapping']['external_product_id']
   result.append({'item_code':code,'source_key':r['source_key'],'verified':True})
  else:
   result.append({'item_code':code,'source_key':r['source_key'],'verified':False})
 assert before=={dt:frappe.db.count(dt) for dt in before}
 if a['apply']:frappe.db.commit()
 else:frappe.db.rollback()
 print(json.dumps({'site':frappe.local.site,'applied':a['apply'],'records':result}))
except BaseException:
 frappe.db.rollback();raise
finally:frappe.destroy()
"""

# Uses WooCommerce CRUD (not raw posts). No REST credentials or external URL.
# Running as one native PHP process per product makes each write recoverable by
# a deterministic SKU+source-key ownership check even if the receipt is lost.
WOO_SCRIPT = r"""
require '/var/www/html/wp-load.php';
$record=json_decode(stream_get_contents(STDIN),true,512,JSON_THROW_ON_ERROR);
if (!class_exists('WooCommerce')) throw new Exception('WooCommerce unavailable');
if (get_option('siteurl')!=='https://shop-test.danks.store' ||
    get_option('woocommerce_coming_soon')!=='yes' ||
    get_option('woocommerce_calc_taxes')!=='no' ||
    (int)wp_count_posts('product')->publish!==0 ||
    count(WC()->payment_gateways()->get_available_payment_gateways())!==0 ||
    count(get_posts(['post_type'=>'shop_webhook','post_status'=>'publish','numberposts'=>1]))!==0 ||
    get_woocommerce_currency()!=='USD')
  throw new Exception('Staging safety drift');
if (!empty($record['item']['has_variants']) || !empty($record['parent_sku']))
  throw new Exception('Variable product not reviewed');
$p=$record['woocommerce'];
if ($p['status']!=='draft' || $p['catalog_visibility']!=='hidden' ||
    $p['manage_stock']!==true || (int)$p['stock_quantity']!==0 ||
    $p['backorders']!=='no' || $record['mapping']['sync_enabled']!==0)
  throw new Exception('Non-sellable draft policy drift');
$sku=$p['sku'];
$source=$record['source_key'];
$meta=[];
foreach ($p['meta_data'] as $m) $meta[$m['key']]=$m['value'];
if (($meta['_rootedops_source_key']??null)!==$source ||
    ($meta['_rootedops_ecwid_enabled']??null)!=='yes' ||
    ($meta['_rootedops_tax_mapping_pending']??null)!=='yes')
  throw new Exception('Provenance or deferred tax policy drift');
$allowed=['16'=>'Gourmet Mushrooms','17'=>'Miscellaneous',
          '18'=>'Grow Kits and Mycology Supplies'];
$catids=[];
foreach ($p['categories'] as $c) {
 $id=(int)$c['id'];$t=get_term($id,'product_cat');
 if (!isset($allowed[(string)$id]) || !$t || is_wp_error($t) ||
     $t->name!==$allowed[(string)$id])
   throw new Exception('Unreviewed destination category');
 $catids[]=$id;
}
$images=[];
foreach ($p['images'] as $img) {
 $id=(int)$img['id'];$file=get_attached_file($id);
 $sha=get_post_meta($id,'_rootedops_media_sha256',true);
 if (!wp_attachment_is_image($id) || !$file || !is_file($file) ||
     !preg_match('/^[0-9a-f]{64}$/D',$sha) || hash_file('sha256',$file)!==$sha)
   throw new Exception('Missing or changed uploaded image');
 $images[]=$id;
}
$id=wc_get_product_id_by_sku($sku);
if ($id) {
 $existing=wc_get_product($id);
 if (!$existing || !$existing->is_type('simple') ||
     $existing->get_meta('_rootedops_source_key',true)!==$source)
   throw new Exception('Existing SKU not owned by migration');
} else {
 $existing=new WC_Product_Simple();
 $existing->set_name($p['name']);
 $existing->set_sku($sku);
 $existing->set_description($p['description']);
 $existing->set_short_description($p['short_description']);
 $existing->set_status('draft');
 $existing->set_catalog_visibility('hidden');
 $existing->set_manage_stock(true);
 $existing->set_stock_quantity(0);
 $existing->set_backorders('no');
 $existing->set_regular_price((string)$p['regular_price']);
 $existing->set_tax_status('none'); // Woo tax calculation remains disabled.
 $existing->set_category_ids($catids);
 if ($images) {
  $existing->set_image_id($images[0]);
  $existing->set_gallery_image_ids(array_slice($images,1));
 }
 foreach ($meta as $k=>$v) $existing->update_meta_data($k,$v);
 $id=$existing->save();
 if (!$id) throw new Exception('Draft save failed');
}
$actual=wc_get_product($id);
if (!$actual || !$actual->is_type('simple') ||
    $actual->get_sku()!==$sku || $actual->get_status()!=='draft' ||
    $actual->get_catalog_visibility()!=='hidden' ||
    !$actual->get_manage_stock() || (int)$actual->get_stock_quantity()!==0 ||
    $actual->get_backorders()!=='no' ||
    $actual->get_name()!==$p['name'] ||
    $actual->get_description()!==$p['description'] ||
    $actual->get_short_description()!==$p['short_description'] ||
    wc_format_decimal($actual->get_regular_price())!==wc_format_decimal($p['regular_price']) ||
    $actual->get_tax_status()!=='none' ||
    $actual->get_meta('_rootedops_source_key',true)!==$source)
 throw new Exception('Draft readback mismatch');
$actualcats=array_map('intval',$actual->get_category_ids());
$expectedcats=$catids;sort($actualcats);sort($expectedcats);
if ($actualcats!==$expectedcats)
 throw new Exception('Category readback mismatch');
$actual_images=array_values(array_filter(array_merge(
 [$actual->get_image_id()],$actual->get_gallery_image_ids())));
if (array_map('intval',$actual_images)!==$images)
 throw new Exception('Media readback mismatch');
foreach ($meta as $k=>$v)
 if ($actual->get_meta($k,true)!=$v)
  throw new Exception('Metadata readback mismatch: '.$k);
$matches=wc_get_products(['sku'=>$sku,'limit'=>-1,'return'=>'ids']);
if (count($matches)!==1 || (int)$matches[0]!==$id)
 throw new Exception('Duplicate Woo SKU');
echo json_encode(['woocommerce_id'=>(int)$id,'sku'=>$sku,
                  'source_key'=>$source,'status'=>'draft',
                  'stock_quantity'=>(int)$actual->get_stock_quantity(),
                  'media_ids'=>$images],JSON_THROW_ON_ERROR);
"""

def run_json(argv,payload,kind):
    proc=subprocess.run(argv,input=json.dumps(payload),text=True,capture_output=True)
    if proc.returncode:
        raise RuntimeError(kind+" native operation failed; exit "+str(proc.returncode)+
                           "; stderr: "+proc.stderr[-1200:])
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(kind+" returned invalid JSON") from error

def persist(path,data):
    private_write(path,data)
    if os.geteuid()==0:
        owner=path.parent.stat()
        os.chown(path,owner.st_uid,owner.st_gid)

def verify_compiled(path,expected_sha):
    if expected_sha!=FIRST_BATCH_SHA:
        raise ValueError("Only exact approved first pilot batch is permitted")
    if compiled_guard(path)!=expected_sha:
        raise ValueError("Compiled batch SHA drift")
    records=records_for_batch(json.loads(path.read_text()))
    if len(records)!=5:
        raise ValueError("First approved import must contain exactly five products")
    if any(r["price"] is None or r["price"]["price_list"]!="Standard Selling"
           or r.get("parent_sku") or r["item"].get("has_variants") for r in records):
        raise ValueError("Only priced simple products are approved")
    keys=[r["source_key"] for r in records]
    if len(set(keys))!=5:
        raise ValueError("Duplicate source keys")
    if {r["mapping"]["external_product_id"] for r in records}!=FIRST_BATCH_IDS:
        raise ValueError("First pilot source identity drift")
    return records

def import_batch(deployment,compiled,sha,receipt_path,apply):
    records=verify_compiled(compiled,sha)
    if not (deployment/".env").is_file() or not (deployment/"docker/docker-compose.yml").is_file():
        raise ValueError("RootedOps deployment not found")
    if receipt_path.exists():
        receipt=json.loads(receipt_path.read_text())
        if receipt.get("compiled_sha256")!=sha or receipt.get("scope")!="erp.danks.store|shop-test.danks.store":
            raise ValueError("Receipt scope/hash drift")
    else:
        receipt={"compiled_sha256":sha,"scope":"erp.danks.store|shop-test.danks.store",
                 "erp_committed":False,"products":{}}
    if receipt_path.parent.stat().st_mode & 0o077:
        raise ValueError("Receipt directory must be 0700")
    if not isinstance(receipt.get("erp_committed"),bool) or not isinstance(receipt.get("products"),dict):
        raise ValueError("Malformed import receipt")
    known={r["source_key"]:r["woocommerce"]["sku"] for r in records}
    if not set(receipt["products"]).issubset(known):
        raise ValueError("Receipt contains unreviewed source identities")
    for key,entry in receipt["products"].items():
        if (entry.get("source_key")!=key or entry.get("sku")!=known[key] or
            type(entry.get("woocommerce_id")) is not int or entry["woocommerce_id"]<=0):
            raise ValueError("Receipt product identity drift")
    guard_live(deployment)
    if not apply:
        return {"apply":False,"source_products":len(records),
                "erp_committed":receipt["erp_committed"],
                "woo_receipted":len(receipt["products"]),"writes":False}
    if os.geteuid()!=0:
        raise ValueError("Native import requires sudo for Docker administration")
    # Product writes follow the separate installed preflight and backup.
    erp=run_json(["docker","compose","--env-file",str(deployment/".env"),
        "-f",str(deployment/"docker/docker-compose.yml"),"exec","-T","-w",
        "/home/frappe/frappe-bench/sites","erpnext-backend",
        "/home/frappe/frappe-bench/env/bin/python","-c",ERP_SCRIPT],
        {"records":records,"apply":True},"ERPNext")
    if len(erp["records"])!=5 or erp["site"]!="erp.danks.store" or not erp["applied"]:
        raise ValueError("ERP native result drift")
    receipt["erp_committed"]=True
    persist(receipt_path,receipt)
    for record in records:
        guard_live(deployment)
        key=record["source_key"]
        woo=run_json(["docker","exec","-i","dank-store-test-dank-wordpress-1",
                      "php","-r",WOO_SCRIPT],record,"WooCommerce")
        if (woo["source_key"]!=key or woo["sku"]!=record["woocommerce"]["sku"] or
            woo["status"]!="draft" or woo["stock_quantity"]!=0):
            raise ValueError("Woo product reconciliation mismatch")
        old=receipt["products"].get(key)
        if old and old["woocommerce_id"]!=woo["woocommerce_id"]:
            raise ValueError("Receipt Woo identity changed")
        receipt["products"][key]=woo
        persist(receipt_path,receipt)
    return {"apply":True,"erp_committed":True,
            "woo_receipted":len(receipt["products"]),"writes":True,
            "receipt":str(receipt_path)}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo-root",type=Path,required=True)
    p.add_argument("--compiled",type=Path,required=True)
    p.add_argument("--sha256",required=True)
    p.add_argument("--receipt",type=Path,required=True)
    p.add_argument("--apply",action="store_true")
    a=p.parse_args()
    result=import_batch(a.repo_root.resolve(),a.compiled,a.sha256,a.receipt,a.apply)
    print(json.dumps(result,indent=2))

if __name__=="__main__":
    main()
