#!/usr/bin/env python3
"""Resume-safe remaining Ecwid catalog migration: source images + draft products.

One operator command, not 110 operator steps. Reads the original immutable
132-product snapshot, skips the 22 accepted source IDs, reuses the existing
147-URL media archive and 22-product destination media receipts. Downloads only
missing required HTTPS images from previously reviewed hosts, then creates
unpublished and out-of-stock ERPNext/WooCommerce catalog records for all 110.
No Ecwid writes. No orders, payments, fulfillment, stock or publication.
"""
import argparse
import base64
from collections import Counter
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
sys.path[:0]=[str(ROOT/"integrations/commerce"),str(HERE)]
from ecwid_migrate import plan, private_write
from reviewed_catalog import compile_catalog
from commerce_full_catalog_preflight import APPROVED_PILOT_IDS, assess
from commerce_production_media import (ERP_PY,WP_PHP,MIMES,SHOP,guard_live,command,save_receipt)
from commerce_production_draft_import import WOO_SCRIPT, run_json
from commerce_catalog_batch import verify_woo
from media_upload import verified_blob
from media import validate_url

SOURCE_SHA="0b4eec40a1cfd1d62551e2ac951a42dac21984f34ffb2d03f9aea697d1d713a8"
SCOPE="erp.danks.store|shop-test.danks.store"
CATEGORIES={"160254004":16,"160255005":17,"160277251":18}
BATCH_SIZE=10

ERP_APPLY=r"""
import sys,json,frappe,rootedops_commerce
from decimal import Decimal
from rootedops_commerce.api import import_product,catalog
data=json.load(sys.stdin)
frappe.init(site='erp.danks.store');frappe.connect();frappe.set_user('Administrator')
try:
 assert rootedops_commerce.__version__=='0.3.1'
 pl=frappe.get_doc('Price List','Standard Selling')
 assert pl.enabled and pl.selling and pl.currency=='USD'
 protected=('Sales Order','Sales Invoice','Payment Entry','Stock Entry','Bin','File')
 before={d:frappe.db.count(d) for d in protected}
 out=[]
 for r in data['records']:
  code=r['item']['item_code'];src=json.loads(r['content']['source_payload'])['product']
  assert src['enabled'] in (True,False) and isinstance(src['enabled'],bool)
  assert r['content']['publication_status']=='Draft'
  assert r['mapping']['site_key']=='95802503' and r['mapping']['sync_enabled']==0
  assert r['item']['item_group']=='Products' and r['item']['stock_uom']=='Nos'
  if frappe.db.exists('Item',code):
   assert not frappe.get_doc('Item',code).is_stock_item
  for image in r['content']['gallery']:
   assert frappe.db.exists('File',{'file_url':image['image'],'is_private':0})
  p=r['price']
  if p:assert p['price_list']=='Standard Selling' and p['currency']=='USD'
  first=import_product({k:r[k] for k in ('item','content','mapping','price')})
  counts={d:frappe.db.count(d) for d in
    ('Item','Commercial Product Content','Commerce Channel Mapping','Item Price')}
  assert import_product({k:r[k] for k in ('item','content','mapping','price')})==first
  assert counts=={d:frappe.db.count(d) for d in counts}
  actual=catalog(code,'Standard Selling')
  assert actual['content']['source_key']==r['source_key']
  assert actual['content']['source_payload']==r['content']['source_payload']
  assert actual['content']['publication_status']=='Draft'
  assert not actual['item']['has_variants'] and not actual['item']['disabled']
  for f in ('public_title','full_description','short_description','seo_title','seo_description'):
   assert (actual['content'].get(f) or '')==(r['content'].get(f) or '')
  assert [(g['image'],g['source_url']) for g in actual['content']['gallery']]==[
    (g['image'],g['source_url']) for g in r['content']['gallery']]
  assert len(actual['mappings'])==1 and not actual['mappings'][0]['sync_enabled']
  assert actual['mappings'][0]['external_product_id']==r['mapping']['external_product_id']
  if p:
   assert len(actual['prices'])==1
   assert Decimal(str(actual['prices'][0]['item_price_rate']))==Decimal(str(p['item_price_rate']))
  else:assert not actual['prices']
  out.append({'source_key':r['source_key'],'item_code':code,'verified':True})
 assert before=={d:frappe.db.count(d) for d in protected}
 frappe.db.commit()
 print(json.dumps({'site':frappe.local.site,'records':out}))
except BaseException:
 frappe.db.rollback();raise
finally:frappe.destroy()
"""

ERP_VERIFY=r"""
import sys,json,frappe,rootedops_commerce
from decimal import Decimal
from rootedops_commerce.api import catalog
data=json.load(sys.stdin)
frappe.init(site='erp.danks.store');frappe.connect();frappe.set_user('Administrator')
try:
 out=[]
 for r in data['records']:
  code=r['item']['item_code']
  item=frappe.get_doc('Item',code)
  assert not item.is_stock_item and item.item_group=='Products' and item.stock_uom=='Nos'
  actual=catalog(code,'Standard Selling')
  assert actual['content']['source_payload']==r['content']['source_payload']
  assert actual['content']['source_key']==r['source_key']
  assert actual['content']['publication_status']=='Draft'
  assert [(g['image'],g['source_url']) for g in actual['content']['gallery']]==[
    (g['image'],g['source_url']) for g in r['content']['gallery']]
  for f in ('public_title','full_description','short_description','seo_title','seo_description'):
   assert (actual['content'].get(f) or '')==(r['content'].get(f) or '')
  assert len(actual['mappings'])==1 and not actual['mappings'][0]['sync_enabled']
  assert actual['mappings'][0]['external_product_id']==r['mapping']['external_product_id']
  if r['price']:
   assert len(actual['prices'])==1
   assert Decimal(str(actual['prices'][0]['item_price_rate']))==Decimal(str(r['price']['item_price_rate']))
  else:assert len(actual['prices'])==0
  out.append(code)
 print(json.dumps({'checked':len(out),'counts':{
    d:frappe.db.count(d) for d in ('Item','Commercial Product Content','Commerce Channel Mapping',
       'Item Price','Sales Order','Sales Invoice','Payment Entry','Stock Entry','Bin')}}))
finally:frappe.db.rollback();frappe.destroy()
"""

WOO_VERIFY=r"""
require '/var/www/html/wp-load.php';
$a=json_decode(stream_get_contents(STDIN),true,512,JSON_THROW_ON_ERROR);
if (!class_exists('WooCommerce') ||
    get_option('siteurl')!=='https://shop-test.danks.store' ||
    get_option('woocommerce_coming_soon')!=='yes' ||
    get_option('woocommerce_calc_taxes')!=='no' ||
    (int)wp_count_posts('product')->publish!==0 ||
    count(WC()->payment_gateways()->get_available_payment_gateways())!==0 ||
    count(get_posts(['post_type'=>'shop_webhook','post_status'=>'publish','numberposts'=>1]))!==0)
 throw new Exception('Woo storefront safety drift');
$results=[];
foreach ($a['records'] as $r) {
 $id=wc_get_product_id_by_sku($r['woocommerce']['sku']);
 $p=wc_get_product($id);
 $e=$r['woocommerce'];
 if (!$p || !$p->is_type('simple') || $p->get_status()!=='draft' ||
     $p->get_catalog_visibility()!=='hidden' || !$p->get_manage_stock() ||
     (int)$p->get_stock_quantity()!==0 || $p->get_stock_status()!=='outofstock' ||
     $p->get_backorders()!=='no' || $p->get_tax_status()!=='none' ||
     $p->get_name()!==$e['name'] ||
     $p->get_description()!==$e['description'] ||
     $p->get_short_description()!==$e['short_description'] ||
     wc_format_decimal($p->get_regular_price())!==wc_format_decimal($e['regular_price']) ||
     $p->get_meta('_rootedops_source_key',true)!==$r['source_key'])
    throw new Exception('Woo product drift: '.$e['sku']);
 foreach ($e['meta_data'] as $m)
  if ($p->get_meta($m['key'],true)!=$m['value'])
   throw new Exception('Woo metadata drift: '.$e['sku']);
 $cats=array_map('intval',$p->get_category_ids());sort($cats);
 $expected=array_map(fn($v)=>(int)$v['id'],$e['categories']);sort($expected);
 if ($cats!==$expected)throw new Exception('Woo categories drift: '.$e['sku']);
 $media=array_values(array_filter(array_merge(
   [$p->get_image_id()],$p->get_gallery_image_ids())));
 $expected=array_map(fn($v)=>(int)$v['id'],$e['images']);
 if (array_map('intval',$media)!==$expected)
   throw new Exception('Woo images drift: '.$e['sku']);
 $results[]=['sku'=>$e['sku'],'id'=>(int)$id,'source_key'=>$r['source_key'],
             'media_ids'=>array_map('intval',$media)];
}
echo json_encode(['records'=>$results,'drafts'=>(int)wp_count_posts('product')->draft,
  'published'=>(int)wp_count_posts('product')->publish],JSON_THROW_ON_ERROR);
"""

WC_CATEGORIES=r"""
require '/var/www/html/wp-load.php';
if (!class_exists('WooCommerce') ||
    get_option('siteurl')!=='https://shop-test.danks.store')throw new Exception('Wrong Woo');
$names=[16=>'Gourmet Mushrooms',17=>'Miscellaneous',18=>'Grow Kits and Mycology Supplies'];
foreach ($names as $id=>$name) {
 $term=get_term($id,'product_cat');
 if (!$term || is_wp_error($term) || $term->name!==$name)
  throw new Exception('Reviewed category drift: '.$id);
}
$id=(int)get_option('default_product_cat');
$term=get_term($id,'product_cat');
if (!$id || !$term || is_wp_error($term) || isset($names[$id]) ||
    strtolower(trim($term->name))!=='uncategorized')
 throw new Exception('Woo default category is not the reviewed Uncategorized category');
echo json_encode(['default_category_id'=>$id],JSON_THROW_ON_ERROR);
"""

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*a,**kw):
        raise ValueError('Image redirect requires separate source review')

def read_source(path):
    data=path.read_bytes()
    if hashlib.sha256(data).hexdigest()!=SOURCE_SHA:
        raise ValueError('Original immutable Ecwid snapshot checksum drift')
    source=json.loads(data)
    overview=assess(source)
    if (overview['total']!=132 or len(overview['cohorts']['validated'])!=22 or
        len(overview['cohorts']['disabled'])!=94 or
        len(overview['cohorts']['other_enabled'])!=16):
        raise ValueError('Full source status/quantity drift')
    planned=plan(source)
    if planned['errors']:raise ValueError('Source plan has unresolved structural errors: '+str(planned['errors'][:5]))
    remaining=[p for p in planned['products'] if int(p['mapping']['external_product_id']) not in APPROVED_PILOT_IDS]
    if len(remaining)!=110 or len({p['content']['item'] for p in remaining})!=110:
        raise ValueError('Remaining catalog identity drift')
    return source,planned,remaining

def required_urls(products):
    return {image['source_url'] for p in products for image in p['content']['gallery']}

def load_archive(path):
    manifest=json.loads((path/'manifest.json').read_text())
    by_url={}
    for row in manifest:
        if row['url'] in by_url and by_url[row['url']]!=row:
            raise ValueError('Conflicting archived URL')
        by_url[row['url']]=row
    return by_url

def media_file(path,row):
    return verified_blob(path,row)

def fetch_missing(urls,archive,existing,receipt_path,extra_hosts):
    previous=json.loads(receipt_path.read_text()) if receipt_path.exists() else {}
    by_url=dict(existing)
    by_url.update(previous)
    approved={urlsplit(url).hostname for url in existing}|set(extra_hosts)
    opener=build_opener(NoRedirect)
    for url in sorted(urls-set(by_url)):
        validate_url(url,approved)
        with opener.open(Request(url,headers={'User-Agent':'RootedOps-Commerce-Archive/0.1'}),timeout=60) as res:
            data=res.read(50*1024*1024+1)
            ctype=res.headers.get('Content-Type','')
        sha=hashlib.sha256(data).hexdigest()
        row={'url':url,'sha256':sha,'bytes':len(data),
             'content_type':ctype,'file':sha}
        if len(data)>50*1024*1024:raise ValueError('Oversized Ecwid source image')
        path=archive/sha
        if path.exists():
            if hashlib.sha256(path.read_bytes()).hexdigest()!=sha:
                raise ValueError('Existing image blob differs')
        else:
            flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW
            fd=os.open(path,flags,0o600)
            if os.geteuid()==0:
                parent=archive.stat()
                os.fchown(fd,parent.st_uid,parent.st_gid)
            with os.fdopen(fd,'wb') as file:file.write(data)
        media_file(archive,row)
        by_url[url]=row
        previous[url]=row
        save_receipt(receipt_path,previous)
    for url in urls:
        media_file(archive,by_url[url])
    return by_url

def require_private_dir(path):
    created=not path.exists()
    path.mkdir(mode=0o700,parents=True,exist_ok=True)
    if path.stat().st_mode & 0o077:raise ValueError('Private state directory must be 0700')
    if created and os.geteuid()==0:
        owner=path.parent.stat()
        os.chown(path,owner.st_uid,owner.st_gid)

def check_pilot_receipts(root):
    directory=root/'media-preparation-1'
    for n,count in ((1,5),(2,5),(3,5),(4,5),(5,2)):
        path=directory/f'pilot-{n:02}-import-receipt.json'
        rec=json.loads(path.read_text())
        if rec.get('erp_committed') is not True or len(rec.get('products',{}))!=count:
            raise ValueError('Accepted 22-product pilot receipt missing or incomplete')
    receipt=json.loads((directory/'media-upload-receipt.json').read_text())
    if receipt.get('scope')!=SCOPE or len(receipt['blobs'])!=11:
        raise ValueError('Pilot media scope/checksum receipt drift')
    rows=json.loads((directory/'uploaded-media.json').read_text())
    return receipt['blobs'],rows

def destination_categories(deployment):
    result=run_json(['docker','exec','-i',SHOP,'php','-r',WC_CATEGORIES],{},'Woo categories')
    return int(result['default_category_id'])

def build_records(planned,remaining,media,default_category):
    selected=deepcopy(planned)
    selected['products']=deepcopy(remaining)
    categories={}
    for p in selected['products']:
        ids=p['category_ids']
        kept=[cid for cid in ids if str(cid) in CATEGORIES]
        # Preserve unclassified POS/legacy category IDs in source payload and
        # metadata rather than assigning them to a false product department.
        if len(kept)!=len(ids) or not kept:
            p['woocommerce']['meta_data'].append({
                'key':'_rootedops_original_ecwid_categories',
                'value':json.dumps(ids)})
        p['category_ids']=kept or ['__rootedops_uncategorized__']
        seen=set()
        gallery=[]
        for img in p['content']['gallery']:
            sha=media[img['source_url']]['sha256']
            if sha not in seen:
                seen.add(sha);gallery.append(img)
        p['content']['gallery']=gallery
    cat_review={str(k):{'woocommerce_id':v} for k,v in CATEGORIES.items()}
    cat_review['__rootedops_uncategorized__']={'woocommerce_id':default_category}
    review={'source_sha256':selected['source_sha256'],'currency':'USD',
            'currency_confirmed':True,'selling_price_list':'Standard Selling',
            'draft_only':True,'include_disabled_drafts':True,
            'allow_unpriced_drafts':True,'defer_tax_mapping':True,
            'categories':cat_review,
            'items':{p['content']['item']:{
                'item_code':p['content']['item'],'item_group':'Products','stock_uom':'Nos'}
                for p in selected['products']}}
    compiled=compile_catalog(selected,review,[media[url] for url in sorted(required_urls(remaining))])
    records=sorted(compiled['records'],key=lambda r:int(r['mapping']['external_product_id']))
    if len(records)!=110:raise ValueError('Compiled full remaining catalog count drift')
    for r in records:
        original=json.loads(r['content']['source_payload'])['product']
        if not isinstance(original.get('enabled'),bool):raise ValueError('Source status missing')
        wc=r['woocommerce']
        wc.update(catalog_visibility='hidden',manage_stock=True,
                  stock_quantity=0,backorders='no')
        if r.get('parent_sku') or r['item'].get('has_variants'):
            raise ValueError('Variable catalog record was not reviewed')
        if wc['regular_price']=='' and r['price'] is not None:
            raise ValueError('Unexpected empty price')
    return records

def erp_command(deployment):
    return ['docker','compose','--env-file',str(deployment/'.env'),
        '-f',str(deployment/'docker/docker-compose.yml'),'exec','-T',
        '-w','/home/frappe/frappe-bench/sites','erpnext-backend',
        '/home/frappe/frappe-bench/env/bin/python','-c',ERP_APPLY]

def upload_images(deployment,archive,needed,existing_urls,pilot_blobs,state):
    receipts_path=state/'remaining-media-receipt.json'
    data=json.loads(receipts_path.read_text()) if receipts_path.exists() else {
        'scope':SCOPE,'blobs':{},'source_sha256':SOURCE_SHA}
    if data.get('scope')!=SCOPE or data.get('source_sha256')!=SOURCE_SHA:
        raise ValueError('Remaining media receipt drift')
    blobs=dict(pilot_blobs)
    blobs.update(data['blobs'])
    for sha in sorted({needed[url]['sha256'] for url in needed}):
        row=next(r for r in needed.values() if r['sha256']==sha)
        content,mime=media_file(archive,row)
        old=blobs.get(sha,{})
        if old.get('erp_file_url') and old.get('woocommerce_media_id'):
            continue
        guard_live(deployment)
        payload={'sha256':sha,'filename':sha+'.'+MIMES[mime],
                 'mime':mime,'blob':base64.b64encode(content).decode()}
        data['blobs'].setdefault(sha,dict(old))
        if not data['blobs'][sha].get('erp_file_url'):
            answer=command(erp_command(deployment)[:-1]+[ERP_PY],payload)
            data['blobs'][sha]['erp_file_url']=answer['file_url']
            save_receipt(receipts_path,data)
        if not data['blobs'][sha].get('woocommerce_media_id'):
            answer=command(['docker','exec','-i',SHOP,'php','-r',WP_PHP],payload)
            data['blobs'][sha]['woocommerce_media_id']=answer['media_id']
            save_receipt(receipts_path,data)
        blobs[sha]=data['blobs'][sha]
    mapped=[]
    for url in sorted(needed):
        row=needed[url]
        dest=blobs[row['sha256']]
        if not dest.get('erp_file_url') or not dest.get('woocommerce_media_id'):
            raise ValueError('Unuploaded image for '+url)
        mapped.append({**row,**dest})
    return mapped

def check_baseline(deployment):
    erp=run_json(erp_command(deployment)[:-1]+[ERP_VERIFY],
        {'records':[]},'ERP baseline')
    woo=run_json(['docker','exec','-i',SHOP,'php','-r',WOO_VERIFY],
        {'records':[]},'Woo baseline')
    if any(erp['counts'][key]!=22 for key in
           ('Item','Commercial Product Content','Commerce Channel Mapping','Item Price')):
        # Resume is handled by the durable full-catalog receipt, not baseline.
        return erp,woo
    if woo['drafts']!=22 or woo['published']!=0:
        raise ValueError('Expected 22 previously accepted Woo drafts')
    return erp,woo

def apply_records(deployment,records,state):
    path=state/'remaining-product-receipt.json'
    raw=json.dumps(records,sort_keys=True,separators=(',',':')).encode()
    sha=hashlib.sha256(raw).hexdigest()
    receipt=json.loads(path.read_text()) if path.exists() else {
        'scope':SCOPE,'source_sha256':SOURCE_SHA,'compiled_sha256':sha,
        'erp_done':[],'woo_done':{}}
    if any(receipt.get(k)!=v for k,v in
           {'scope':SCOPE,'source_sha256':SOURCE_SHA,'compiled_sha256':sha}.items()):
        raise ValueError('Bulk receipt or compiled catalog drift')
    keys={r['source_key'] for r in records}
    if not set(receipt['erp_done']).issubset(keys) or not set(receipt['woo_done']).issubset(keys):
        raise ValueError('Foreign receipt identity')
    for start in range(0,len(records),BATCH_SIZE):
        chunk=records[start:start+BATCH_SIZE]
        guard_live(deployment)
        result=run_json(erp_command(deployment),{'records':chunk},'ERPNext catalog import')
        if (result['site']!='erp.danks.store' or
            {x['source_key'] for x in result['records']}!={x['source_key'] for x in chunk}):
            raise ValueError('ERPNext chunk readback drift')
        receipt['erp_done']=sorted(set(receipt['erp_done'])|
                                   {r['source_key'] for r in chunk})
        save_receipt(path,receipt)
        for r in chunk:
            guard_live(deployment)
            result=run_json(['docker','exec','-i',SHOP,'php','-r',WOO_SCRIPT],
                r,'WooCommerce product import')
            key=r['source_key']
            if result['source_key']!=key or result['sku']!=r['woocommerce']['sku']:
                raise ValueError('WooCommerce source identity drift')
            previous=receipt['woo_done'].get(key)
            if previous and previous['woocommerce_id']!=result['woocommerce_id']:
                raise ValueError('WooCommerce replay changed product ID')
            receipt['woo_done'][key]=result
            save_receipt(path,receipt)
    if len(receipt['erp_done'])!=110 or len(receipt['woo_done'])!=110:
        raise ValueError('Incomplete bulk receipt')
    return receipt,sha

def reconcile(deployment,records,receipt):
    erp=run_json(erp_command(deployment)[:-1]+[ERP_VERIFY],{'records':records},
                 'ERP final reconciliation')
    woo=run_json(['docker','exec','-i',SHOP,'php','-r',WOO_VERIFY],
                 {'records':records},'Woo final reconciliation')
    if erp['checked']!=110 or len(woo['records'])!=110:
        raise ValueError('Remaining product reconciliation count drift')
    expected_prices=22+sum(r['price'] is not None for r in records)
    if (any(erp['counts'][k]!=132 for k in
            ('Item','Commercial Product Content','Commerce Channel Mapping')) or
        erp['counts']['Item Price']!=expected_prices or
        any(erp['counts'][k]!=0 for k in
            ('Sales Order','Sales Invoice','Payment Entry','Stock Entry','Bin')) or
        woo['drafts']!=132 or woo['published']!=0):
        raise ValueError('Final catalog safety/count reconciliation drift')
    for result in woo['records']:
        saved=receipt['woo_done'][result['source_key']]
        if any(result[k]!=saved[k] for k in
               ('source_key','sku','media_ids','woocommerce_id')):
            raise ValueError('Saved Woo product receipt mismatch')
    return {'status':'PASSED','erp':erp['counts'],'woo_drafts':woo['drafts'],
            'published':0,'remaining_checked':110,
            'receipt_matches':True,'writes_during_verification':False}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo-root',type=Path,required=True)
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--archive',type=Path,required=True)
    p.add_argument('--state-dir',type=Path,required=True)
    p.add_argument('--allow-host',action='append',default=[])
    p.add_argument('--apply',action='store_true')
    args=p.parse_args()
    deployment=args.repo_root.resolve()
    source,planned,remaining=read_source(args.source)
    if not (deployment/'.env').is_file() or not (deployment/'docker/docker-compose.yml').is_file():
        raise ValueError('Production deployment checkout required')
    existing=load_archive(args.archive)
    needed=required_urls(remaining)
    archived=needed & set(existing)
    missing=needed-set(existing)
    report={'remaining_products':len(remaining),
            'source_enabled':sum(p['source_enabled'] for p in remaining),
            'source_disabled':sum(not p['source_enabled'] for p in remaining),
            'required_image_urls':len(needed),
            'already_archived_urls':len(archived),
            'download_needed_urls':len(missing),
            'missing_image_products':sum(not p['content']['gallery'] for p in remaining),
            'unpriced_products':sum(p['price'] is None for p in remaining),
            'writes':args.apply}
    if not args.apply:
        print(json.dumps(report,indent=2));return
    if os.geteuid()!=0:raise ValueError('Use sudo for native Docker catalog import')
    require_private_dir(args.state_dir)
    pilot_blobs,pilot_media=check_pilot_receipts(args.state_dir.parent)
    guard_live(deployment)
    baseline_erp,baseline_woo=check_baseline(deployment)
    if (baseline_erp['counts']['Item']==22 and baseline_woo['drafts']!=22):
        raise ValueError('ERP/Woo pre-import identity discrepancy')
    archive_rows=fetch_missing(needed,args.archive,existing,
                              args.state_dir/'new-media-urls.json',args.allow_host)
    media=upload_images(deployment,args.archive,
                        {u:archive_rows[u] for u in needed},pilot_media,
                        pilot_blobs,args.state_dir)
    default_category=destination_categories(deployment)
    mapped={row['url']:row for row in media}
    records=build_records(planned,remaining,mapped,default_category)
    receipt,sha=apply_records(deployment,records,args.state_dir)
    result=reconcile(deployment,records,receipt)
    report.update({'compiled_sha256':sha,'media_upload_urls':len(media),
                   'woo_default_category':default_category,'reconciliation':result})
    save_receipt(args.state_dir/'remaining-final-report.json',report)
    print(json.dumps(report,indent=2))

if __name__=='__main__':
    main()
