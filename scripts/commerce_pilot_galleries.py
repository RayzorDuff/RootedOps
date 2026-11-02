#!/usr/bin/env python3
"""Update only the existing three pilot galleries, retaining immutable CSV content.

Run after commerce_prepare_real_batch.py --batch 0. Uses installed File/content
models and the existing Woo adapter. Source API snapshots remain private alongside
the original CSV payload and new media receipts; no source identity is rewritten.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'integrations/commerce'))
from ecwid_migrate import api, private_write
from channel import upsert_draft
from commerce_catalog_batch import guarded_environment
from commerce_pilot_prices import pilot_records

NATIVE = '''import json,sys,frappe
a=json.load(sys.stdin);frappe.init(site='erp-test2.danks.store');frappe.connect();frappe.set_user('Administrator')
try:
 assert frappe.conf.get('maintenance_mode') and frappe.conf.get('pause_scheduler')
 for dt,f in [('Email Account',{'enable_outgoing':1}),('Webhook',{'enabled':1}),('Notification',{'enabled':1})]:assert not frappe.db.count(dt,f)
 protected=['Item','Item Price','File','Commerce Channel Mapping','Sales Order','Sales Invoice','Payment Entry','Stock Entry','Bin']
 counts={dt:frappe.db.count(dt) for dt in protected}
 out=[]
 for r,old in zip(a['records'],a['old']):
  code=r['content']['item'];c=frappe.get_doc('Commercial Product Content',code)
  assert c.source_key==old['source_key']==r['source_key'] and c.source_payload==old['content']['source_payload'] and c.publication_status=='Draft'
  assert all(not m.sync_enabled for m in frappe.get_all('Commerce Channel Mapping',filters={'item':code},fields=['sync_enabled']))
  preserve={k:c.get(k) for k in ['source_key','source_payload','public_title','short_description','full_description','seo_title','seo_description','publication_status']}
  desired=[{'image':g['image'],'source_url':g['source_url']} for g in r['content']['gallery']]
  for g in desired:assert frappe.db.exists('File',{'file_url':g['image']})
  for replay in range(2):
   current=[{'image':g.image,'source_url':g.source_url} for g in c.gallery]
   if current!=desired:c.set('gallery',desired);c.save()
   c.reload();assert [{ 'image':g.image,'source_url':g.source_url} for g in c.gallery]==desired
   assert preserve=={k:c.get(k) for k in preserve}
   if not replay:children=[g.name for g in c.gallery]
   else:assert children==[g.name for g in c.gallery]
  out.append({'erp_item':code,'gallery_count':len(c.gallery),'immutable_source_preserved':True})
 assert counts=={dt:frappe.db.count(dt) for dt in protected}
 frappe.db.commit();print(json.dumps(out))
except Exception:frappe.db.rollback();raise
finally:frappe.destroy()
'''


def run(environment):
    target, private = guarded_environment(environment)
    work = private / 'catalog-expansion/batch-0'
    document = json.loads((work / 'compiled.json').read_text())
    original = pilot_records(json.loads((private / 'ecwid-pilot/plan.json').read_text()))
    indexed = {r['source_key']: r for r in document['records']}
    if set(indexed) != {r['source_key'] for r in original}:
        raise ValueError('Exact existing pilot source identities required')
    records = [indexed[r['source_key']] for r in original]
    credentials = json.loads((private / 'wordpress-credentials.json').read_text())
    auth = 'Basic ' + base64.b64encode((credentials['username'] + ':' + credentials['application_password']).encode()).decode()
    root = target['shop'] + '/wp-json/wc/v3/products/'
    ids = {'610274980': 18, '610274742': 20, '711334880': 22}
    before = []
    for r in records:
        actual = api(root + str(ids[r['mapping']['external_product_id']]) + '?context=edit', auth)
        meta = {m['key']: m['value'] for m in actual['meta_data']}
        if (actual['sku'] != r['woocommerce']['sku'] or actual['status'] != 'draft'
                or actual['type'] != 'simple' or actual['stock_quantity'] != 0 or not actual['manage_stock']
                or actual['catalog_visibility'] != 'hidden' or meta.get('_rootedops_source_key') != r['source_key']):
            raise ValueError('Pilot ownership/isolation drift')
        before.append(actual)
    native = subprocess.run(['docker', 'exec', '-i', '-w', '/home/frappe/frappe-bench/sites',
                             'rootedops-full-test-erpnext-backend-1', '/home/frappe/frappe-bench/env/bin/python', '-c', NATIVE],
                            input=json.dumps({'records': records, 'old': original}), text=True, capture_output=True)
    if native.returncode:
        private_write(work / 'gallery-error.json', {'stdout': native.stdout, 'stderr': native.stderr})
        raise RuntimeError('ERP gallery transaction failed; inspect private diagnostics')
    report = {'erp': json.loads(native.stdout), 'products': [],
              'compiled_sha256': hashlib.sha256((work / 'compiled.json').read_bytes()).hexdigest()}
    private_write(work / 'gallery-applied.json', report)
    for r, old in zip(records, before):
        projection = {'source_key': r['source_key'], 'item': {}, 'woocommerce': {
            'sku': old['sku'], 'status': 'draft', 'images': r['woocommerce']['images']}}
        first = upsert_draft(target['shop'], auth, projection)
        second = upsert_draft(target['shop'], auth, projection)
        actual = api(root + str(old['id']) + '?context=edit', auth)
        if first['id'] != second['id'] or second['id'] != old['id']:
            raise ValueError('Pilot ID changed')
        expected = [i['id'] for i in r['woocommerce']['images']]
        if [i['id'] for i in actual['images']] != expected or len(expected) != len(set(expected)):
            raise ValueError('Gallery ordering/duplicates differ')
        for field in ('sku','status','type','catalog_visibility','stock_quantity','manage_stock','regular_price',
                      'description','short_description','categories','meta_data','tax_class','tax_status'):
            if actual[field] != old[field]:
                raise ValueError('Unrelated pilot field changed: ' + field)
        report['products'].append({'ecwid_product_id': r['mapping']['external_product_id'],
                                   'woo_id': actual['id'], 'gallery_ids': expected})
        private_write(work / 'gallery-applied.json', report)
    print(json.dumps(report))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('environment', type=Path)
    run(p.parse_args().environment)
