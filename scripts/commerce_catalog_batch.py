#!/usr/bin/env python3
"""Apply one reviewed real catalog batch through existing installed import adapters.

Read-only by default. Input is migrate_reviewed.py's compiled output, with every
media blob already archived/uploaded. No source extraction, credential generation,
infrastructure changes, historical orders, stock activation or publication.
"""
import argparse
import base64
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'integrations/commerce'))
from channel import upsert_draft
from ecwid_migrate import api, private_write
from reviewed_catalog import money
from commerce_staging_targets import targets


def records_for_batch(document):
    for field in ('source_sha256', 'review_sha256'):
        value = document.get(field, '')
        if len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
            raise ValueError('Compiled source/review hashes required')
    records = deepcopy(document['records'])
    if not 1 <= len(records) <= 5:
        raise ValueError('Select one complete family or batch of at most five records')
    keys, skus, codes = set(), set(), set()
    for r in records:
        m, wc = r['mapping'], r['woocommerce']
        key, sku, code = r['source_key'], wc['sku'], r['item']['item_code']
        expected = 'ecwid:95802503:product:' + m['external_product_id']
        if m.get('external_variation_id'):
            expected += ':variation:' + m['external_variation_id']
        if (key != expected or m['provider'] != 'ecwid' or m['site_key'] != '95802503'
                or not m['external_product_id'].isdigit() or key in keys
                or sku.casefold() in skus or code in codes
                or m.get('sync_enabled', 0) != 0 or m['item'] != code
                or r['content']['item'] != code or r['content']['source_key'] != key
                or m['external_sku'] != sku or r['expected_currency'] != 'USD'
                or wc.get('status') != 'draft' or r['content']['publication_status'] != 'Draft'):
            raise ValueError('Real source identity/draft/currency drift')
        source = json.loads(r['content']['source_payload'])
        if str(source['product']['id']) != m['external_product_id'] or source['product'].get('enabled') is not True:
            raise ValueError('Enabled original source payload required')
        if not r['item'].get('has_variants') and not r.get('parent_sku'):
            product = source['product']
            if ('options' not in product or '_combinations' not in product
                    or product['options'] or product['_combinations']):
                raise ValueError('Verified empty source options/combinations required for simple batch')
        original = source.get('variation') or source['product']
        if original['sku'] != sku or (source.get('variation') is None) != (not m.get('external_variation_id')):
            raise ValueError('Original SKU/variation drift')
        if source.get('variation') and str(original['id']) != m['external_variation_id']:
            raise ValueError('Original variation identity drift')
        meta = {v['key']: v['value'] for v in wc['meta_data']}
        if meta.get('_rootedops_source_key') != key:
            raise ValueError('Woo source metadata required')
        if r['price']:
            if (r['price']['currency'] != 'USD' or
                    Decimal(money(r['price']['item_price_rate'])) != Decimal(money(original['price'])) or
                    Decimal(money(wc['regular_price'])) != Decimal(money(original['price']))):
                raise ValueError('Authentic source USD rate required')
        elif not r['item'].get('has_variants'):
            raise ValueError('Every sellable record requires a reviewed price')
        images = [i['id'] for i in wc.get('images', [])]
        if len(images) != len(set(images)) or any(type(i) is not int or i <= 0 for i in images):
            raise ValueError('Unique uploaded media identities required')
        if len(images) != len(r['content'].get('gallery', [])):
            raise ValueError('ERP/Woo gallery count differs')
        wc.update(catalog_visibility='hidden', manage_stock=True, stock_quantity=0, backorders='no')
        keys.add(key); skus.add(sku.casefold()); codes.add(code)
    for r in records:
        if r.get('parent_sku') and not any(p['woocommerce']['sku'] == r['parent_sku'] and p['item'].get('has_variants') for p in records):
            raise ValueError('Complete reviewed variation family required in batch')
    return sorted(records, key=lambda r: bool(r.get('parent_sku')))


NATIVE = '''import json,sys,frappe,rootedops_commerce
from decimal import Decimal
from rootedops_commerce.api import import_product,catalog
a=json.load(sys.stdin);frappe.init(site='erp-test2.danks.store');frappe.connect();frappe.set_user('Administrator')
try:
 assert rootedops_commerce.__version__=='0.3.1'
 assert frappe.conf.get('maintenance_mode') and frappe.conf.get('pause_scheduler')
 for dt,f in [('Email Account',{'enable_outgoing':1}),('Webhook',{'enabled':1}),('Notification',{'enabled':1})]:assert frappe.db.count(dt,f)==0
 protected=['Sales Order','Sales Invoice','Payment Entry','Stock Entry','Bin','File']
 before={dt:frappe.db.count(dt) for dt in protected}
 all_counts=['Item','Commercial Product Content','Commerce Channel Mapping','Item Price']
 out=[]
 for r in a['records']:
  code=r['item']['item_code'];existing=frappe.db.exists('Commercial Product Content',code)
  for dt,value in [('Item Group',r['item']['item_group']),('UOM',r['item']['stock_uom'])]:assert frappe.db.exists(dt,value),(dt,value)
  if r['price']:
   pl=frappe.get_doc('Price List',r['price']['price_list']);assert pl.currency=='USD' and pl.selling and pl.enabled
  for tax in r['item'].get('taxes',[]):assert frappe.db.exists('Item Tax Template',tax['item_tax_template'])
  for media in r['content'].get('gallery',[]):
   assert media['image'].startswith('/files/') and frappe.db.exists('File',{'file_url':media['image']})
  if existing:
   c=frappe.get_doc('Commercial Product Content',code)
   assert c.source_key==r['source_key'] and c.source_payload==r['content']['source_payload'] and c.publication_status=='Draft'
  if a['apply']:
   payload={k:r[k] for k in ['item','content','mapping','price']}
   first=import_product(payload)
   count={dt:frappe.db.count(dt) for dt in all_counts}
   assert import_product(payload)==first
   assert count=={dt:frappe.db.count(dt) for dt in all_counts}
   actual=catalog(code,r['price']['price_list'] if r['price'] else None)
   c=actual['content']
   for field in ['public_title','full_description','short_description','seo_title','seo_description','source_key','source_payload']:
    assert (c.get(field) or '')==(r['content'].get(field) or ''),(code,field)
   assert c['publication_status']=='Draft' and all(not m.sync_enabled for m in actual['mappings'])
   assert [g['image'] for g in c['gallery']]==[g['image'] for g in r['content'].get('gallery',[])]
   assert [g['source_url'] for g in c['gallery']]==[g['source_url'] for g in r['content'].get('gallery',[])]
   if r['price']:
    assert len(actual['prices'])==1
    assert Decimal(str(actual['prices'][0]['item_price_rate']))==Decimal(str(r['price']['item_price_rate']))
   out.append({'erp_item':code,'installed_verified':True,'price_id':actual['prices'][0]['name'] if r['price'] else None})
  else:out.append({'erp_item':code,'existing_content':bool(existing),'installed_verified':False})
 assert before=={dt:frappe.db.count(dt) for dt in protected}
 if a['apply']:frappe.db.commit()
 else:frappe.db.rollback()
 print(json.dumps(out))
except Exception:frappe.db.rollback();raise
finally:frappe.destroy()
'''


def guarded_environment(environment):
    env = environment.resolve(); target = targets(env)
    if target['erp'] != 'https://erp-test2.danks.store' or target['shop'] != 'https://shop-test2.danks.store':
        raise ValueError('Test2 only')
    private = env / 'private'
    if json.loads((private / 'wordpress-offline-receipt.json').read_text())['controls'] != {
            'cron_disabled': True, 'http_blocked': True, 'mail_blocked': True, 'payment_gateways': 0}:
        raise ValueError('Offline shop receipt required')
    for name, project in [('rootedops-full-test-erpnext-backend-1', 'rootedops-full-test'),
                          ('dank-store-test-dank-wordpress-1', 'dank-store-test')]:
        c = json.loads(subprocess.check_output(['docker', 'inspect', name]))[0]
        if (c['Config']['Labels'].get('com.docker.compose.project') != project
                or not c['State']['Running'] or any((c['NetworkSettings']['Ports'] or {}).values())):
            raise ValueError('Isolated running container required')
        for network in c['NetworkSettings']['Networks']:
            if not json.loads(subprocess.check_output(['docker', 'network', 'inspect', network]))[0]['Internal']:
                raise ValueError('Internal container network required')
    # Recheck live controls; a historical installation receipt alone is insufficient.
    php = """require '/var/www/html/wp-load.php';
echo json_encode(['cron'=>defined('DISABLE_WP_CRON') && DISABLE_WP_CRON,
'http'=>defined('WP_HTTP_BLOCK_EXTERNAL') && WP_HTTP_BLOCK_EXTERNAL,
'mail'=>has_filter('pre_wp_mail','__return_true')!==false,
'gateways'=>count(WC()->payment_gateways()->get_available_payment_gateways())]);"""
    live = json.loads(subprocess.check_output(['docker', 'exec', 'dank-store-test-dank-wordpress-1', 'php', '-r', php]))
    if live != {'cron': True, 'http': True, 'mail': True, 'gateways': 0}:
        raise ValueError('Live shop isolation controls drifted')
    return target, private


def verify_woo(actual, record):
    wc = record['woocommerce']
    for field in ('sku', 'status', 'catalog_visibility', 'manage_stock', 'stock_quantity', 'backorders',
                  'name', 'description', 'short_description', 'tax_status', 'tax_class'):
        if field in wc and actual.get(field) != wc[field]:
            raise ValueError('Woo read-back mismatch: ' + field)
    if record['price'] and Decimal(actual['regular_price']) != Decimal(wc['regular_price']):
        raise ValueError('Woo price mismatch')
    if [i['id'] for i in actual.get('images', [])] != [i['id'] for i in wc.get('images', [])]:
        raise ValueError('Woo ordered gallery mismatch')
    if sorted(i['id'] for i in actual.get('categories', [])) != sorted(i['id'] for i in wc.get('categories', [])):
        raise ValueError('Woo category mismatch')
    meta = {m['key']: m['value'] for m in actual['meta_data']}
    if any(meta.get(m['key']) != m['value'] for m in wc['meta_data']):
        raise ValueError('Woo provenance/SEO mismatch')


def run(environment, compiled_path, expected_sha256, apply=False):
    if os.geteuid() != 0:
        raise ValueError('Use existing sudo -n authorization inside the console lock')
    raw = compiled_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError('Compiled batch hash drift')
    records = records_for_batch(json.loads(raw))
    if any(r.get('parent_sku') or r['item'].get('has_variants') for r in records):
        raise ValueError('This batch runner handles verified simple products only; preserve variable families for separate acceptance')
    target, private = guarded_environment(environment)
    receipt_dir = private / 'catalog-batches'; receipt_dir.mkdir(mode=0o700, exist_ok=True)
    receipt = receipt_dir / (expected_sha256 + ('-applied.json' if apply else '-preflight.json'))
    credentials = json.loads((private / 'wordpress-credentials.json').read_text())
    auth = 'Basic ' + base64.b64encode((credentials['username'] + ':' + credentials['application_password']).encode()).decode()
    root = target['shop'] + '/wp-json/wc/v3/'
    if api(root + 'settings/general/woocommerce_currency', auth)['value'] != 'USD':
        raise ValueError('USD store required')
    if api(root + 'webhooks?status=active&per_page=100', auth):
        raise ValueError('Active Woo webhooks are forbidden for catalog batches')
    old = {}
    for r in records:
        found = api(root + 'products?' + urlencode({'sku': r['woocommerce']['sku'], 'context': 'edit', 'per_page': 100}), auth)
        if len(found) > 1:
            raise ValueError('Ambiguous destination SKU')
        if found:
            p = found[0]; meta = {m['key']: m['value'] for m in p['meta_data']}
            if (p['sku'] != r['woocommerce']['sku'] or meta.get('_rootedops_source_key') != r['source_key']
                    or p['status'] != 'draft' or p['catalog_visibility'] != 'hidden'
                    or p['stock_quantity'] != 0 or not p['manage_stock']):
                raise ValueError('Existing destination ownership/isolation drift')
        old[r['source_key']] = found[0]['id'] if found else None
        for image in r['woocommerce'].get('images', []):
            media = api(target['shop'] + '/wp-json/wp/v2/media/' + str(image['id']), auth)
            if media['id'] != image['id'] or not media['mime_type'].startswith('image/'):
                raise ValueError('Uploaded image unavailable')
    native = subprocess.run(['docker', 'exec', '-i', '-w', '/home/frappe/frappe-bench/sites',
                             'rootedops-full-test-erpnext-backend-1', '/home/frappe/frappe-bench/env/bin/python', '-c', NATIVE],
                            input=json.dumps({'records': records, 'apply': apply}), text=True, capture_output=True)
    if native.returncode:
        private_write(receipt_dir / (expected_sha256 + '-erp-error.json'), {'stdout': native.stdout, 'stderr': native.stderr})
        raise RuntimeError('ERP batch failed; private diagnostics saved; transaction rolled back')
    result = {'compiled_sha256': expected_sha256, 'applied': apply, 'erp': json.loads(native.stdout), 'products': []}
    private_write(receipt, result)  # ERP may already be committed; preserve that checkpoint.
    for r, erp in zip(records, result['erp']):
        if apply:
            one = upsert_draft(target['shop'], auth, r, attributes=r.get('variant_attributes'))
            private_write(receipt_dir / (expected_sha256 + '-woo-pending.json'), {'source_key': r['source_key'], 'woo_id': one['id']})
            # Replay must reuse the same product and media relationships.
            two = upsert_draft(target['shop'], auth, r, attributes=r.get('variant_attributes'))
            actual = api(root + 'products/' + str(two['id']) + '?context=edit', auth)
            if one['id'] != two['id'] or (old[r['source_key']] and old[r['source_key']] != two['id']):
                raise ValueError('Woo identity changed on replay')
            verify_woo(actual, r)
            matches = api(root + 'products?' + urlencode({'sku': r['woocommerce']['sku'], 'context': 'edit', 'per_page': 100}), auth)
            if len(matches) != 1 or matches[0]['id'] != actual['id']:
                raise ValueError('Woo duplicate after replay')
            result['products'].append(dict(erp, ecwid_product_id=r['mapping']['external_product_id'],
                                          woo_id=actual['id'], price=actual['regular_price'],
                                          media_ids=[i['id'] for i in actual['images']]))
            private_write(receipt, result)
    print(json.dumps({'applied': apply, 'records': len(records), 'verified': len(result['products']), 'receipt': str(receipt)}))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('environment', type=Path); p.add_argument('compiled', type=Path)
    p.add_argument('--sha256', required=True); p.add_argument('--apply', action='store_true')
    a = p.parse_args(); run(a.environment, a.compiled, a.sha256, a.apply)
