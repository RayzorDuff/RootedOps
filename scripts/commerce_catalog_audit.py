#!/usr/bin/env python3
"""Read back real installed catalog identities or verify stored media binaries.

Requires the command-scoped lock. Does not replay imports or create documents.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'integrations/commerce'))
from ecwid_migrate import api, private_write
from commerce_catalog_batch import guarded_environment, verify_woo, records_for_batch

MEDIA_NATIVE = '''import json,sys,hashlib,frappe
a=json.load(sys.stdin);frappe.init(site='erp-test2.danks.store');frappe.connect()
try:
 aliases={}
 for row in a:
  files=frappe.get_all('File',filters={'file_url':row['erp_file_url']},fields=['name']);assert files
  aliases[row['erp_file_url']]=len(files)
  for f in files:
   blob=frappe.get_doc('File',f.name).get_content()
   if isinstance(blob,str):blob=blob.encode()
   assert hashlib.sha256(blob).hexdigest()==row['sha256']
 print(json.dumps({'erp_originals_verified':len(a),'erp_file_alias_counts':aliases}))
finally:frappe.db.rollback();frappe.destroy()
'''

CATALOG_NATIVE = '''import json,sys,frappe
from decimal import Decimal
from rootedops_commerce.api import catalog
a=json.load(sys.stdin);frappe.init(site='erp-test2.danks.store');frappe.connect();frappe.set_user('Administrator')
try:
 real=frappe.get_all('Commercial Product Content',filters={'source_key':['like','ecwid:95802503:product:%']},fields=['item','source_key','publication_status'])
 assert len(real)==len(a['expected'])==22
 assert {r.source_key for r in real}=={r['source_key'] for r in a['expected']}
 result=[]
 for r in a['expected']:
  c=catalog(r['sku'],'Ecwid Catalog Pilot USD');assert c['content']['source_key']==r['source_key'] and c['content']['publication_status']=='Draft'
  assert len(c['prices'])==1 and Decimal(str(c['prices'][0]['item_price_rate']))==Decimal(r['price'])
  assert len(c['mappings'])==1 and not c['mappings'][0]['sync_enabled']
  result.append({'ecwid_product_id':r['id'],'erp_item':r['sku'],'price_id':c['prices'][0]['name'],'price':str(c['prices'][0]['item_price_rate'])})
 print(json.dumps({'products':result,'item_prices':len(result),'financial_counts':{dt:frappe.db.count(dt) for dt in ['Sales Order','Sales Invoice','Payment Entry']}}))
finally:frappe.db.rollback();frappe.destroy()
'''


def native(code, value):
    p = subprocess.run(['docker', 'exec', '-i', '-w', '/home/frappe/frappe-bench/sites',
                        'rootedops-full-test-erpnext-backend-1', '/home/frappe/frappe-bench/env/bin/python', '-c', code],
                       input=json.dumps(value), capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError(p.stderr[-1400:])
    return json.loads(p.stdout)


def run(environment, media_batch=None):
    target, private = guarded_environment(environment)
    if media_batch is not None:
        work = private / 'catalog-expansion' / ('batch-' + str(media_batch))
        rows = json.loads((work / 'uploaded-media.json').read_text())
        erp = native(MEDIA_NATIVE, rows)
        expected = {str(r['woocommerce_media_id']): r['sha256'] for r in rows}
        php = """require '/var/www/html/wp-load.php';$expected=json_decode(base64_decode('%s'),true);$out=[];
foreach($expected as $id=>$sha){$path=wp_get_original_image_path((int)$id);if(!$path || !is_file($path) || hash_file('sha256',$path)!==$sha){throw new Exception('Original media checksum mismatch');}$out[]=['id'=>(int)$id,'sha256'=>$sha,'original_preserved'=>true];}echo json_encode($out);""" % base64.b64encode(json.dumps(expected).encode()).decode()
        woo = json.loads(subprocess.check_output(['docker', 'exec', 'dank-store-test-dank-wordpress-1', 'php', '-r', php]))
        report = dict(erp, woo_originals=woo, batch=media_batch)
        private_write(work / 'media-binary-audit.json', report)
        print(json.dumps({'batch': media_batch, 'erp_originals': erp['erp_originals_verified'], 'woo_originals': len(woo)})); return
    expected, compiled = [], []
    for batch in range(1, 5):
        path = private / 'catalog-expansion' / ('batch-' + str(batch)) / 'compiled.json'
        records = records_for_batch(json.loads(path.read_text())); compiled.extend(records)
        for r in records:
            expected.append({'id': r['mapping']['external_product_id'], 'sku': r['woocommerce']['sku'],
                             'source_key': r['source_key'], 'price': r['woocommerce']['regular_price']})
    pilot = json.loads((private / 'ecwid-pilot/plan.json').read_text())['products']
    for r in pilot:
        expected.append({'id': r['mapping']['external_product_id'], 'sku': r['content']['item'],
                         'source_key': r['source_key'], 'price': str(r['price'])})
    erp = native(CATALOG_NATIVE, {'expected': expected})
    c = json.loads((private / 'wordpress-credentials.json').read_text())
    auth = 'Basic ' + base64.b64encode((c['username'] + ':' + c['application_password']).encode()).decode()
    products = api(target['shop'] + '/wp-json/wc/v3/products?context=edit&per_page=100&status=any', auth)
    real = [p for p in products if any(m['key'] == '_rootedops_source_key' and str(m['value']).startswith('ecwid:95802503:product:') for m in p['meta_data'])]
    if len(real) != len(expected):
        raise ValueError('Global Woo product count differs')
    by_sku = {p['sku']: p for p in real}
    if len(by_sku) != len(real):
        raise ValueError('Duplicate real Woo SKU')
    for r in compiled:
        verify_woo(by_sku[r['woocommerce']['sku']], r)
    for p in real:
        if p['status'] != 'draft' or p['catalog_visibility'] != 'hidden' or p['stock_quantity'] != 0 or not p['manage_stock']:
            raise ValueError('Global publication/stock drift')
    mappings = [dict(r, woo_id=by_sku[r['erp_item']]['id'], installed_verified=True,
                     gallery_count=len(by_sku[r['erp_item']]['images'])) for r in erp['products']]
    source = json.loads(Path('/home/rootedops/.local/state/commerce-ecwid-read/public-products.json').read_text())
    enabled = [p for p in source['products'] if p.get('enabled')]
    report = {'installed_products': len(real), 'new_products': len(compiled), 'enabled_source': len(enabled),
              'disabled_placeholders': len(source['products'])-len(enabled), 'products': mappings,
              'source_options_present': sum(bool(p.get('options')) for p in enabled),
              'source_combinations_present': sum(bool(p.get('combinations')) for p in enabled),
              'variation_fields_present': all('options' in p and 'combinations' in p for p in enabled),
              'tax_calculation': api(target['shop']+'/wp-json/wc/v3/settings/general/woocommerce_calc_taxes',auth)['value'],
              'tax_mapping_pending': True, 'financial_counts': erp['financial_counts']}
    private_write(private / 'catalog-expansion/catalog-audit.json', report)
    print(json.dumps(report))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('environment', type=Path)
    p.add_argument('--media-batch', type=int, choices=range(0, 5)); a = p.parse_args(); run(a.environment, a.media_batch)
