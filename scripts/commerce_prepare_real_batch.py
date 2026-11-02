#!/usr/bin/env python3
"""Prepare one existing Ecwid candidate batch with original media and source lineage.

Uses the existing planner, media archiver/uploader and reviewed compiler. Native
ERP File transport is necessary while the restored ERP HTTP site is isolated.
Never imports a product itself. Every invocation belongs inside the console lock.
"""
import argparse
import base64
from email.parser import BytesParser
from email import policy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlencode, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'integrations/commerce'))
from ecwid_migrate import api, plan, private_write
from media import archive
from media_upload import upload, upload_request
from reviewed_catalog import compile_catalog
from commerce_catalog_batch import guarded_environment, records_for_batch

SOURCE = Path('/home/rootedops/.local/state/commerce-ecwid-read')
CDN = 'd2j6dbq0eux0bg.cloudfront.net'

FILE_NATIVE = '''import sys,json,base64,hashlib,frappe
from frappe.utils.file_manager import save_file
a=json.load(sys.stdin);frappe.init(site='erp-test2.danks.store');frappe.connect();frappe.set_user('Administrator')
try:
 assert frappe.conf.get('maintenance_mode') and frappe.conf.get('pause_scheduler')
 for dt,f in [('Email Account',{'enable_outgoing':1}),('Webhook',{'enabled':1}),('Notification',{'enabled':1})]:assert not frappe.db.count(dt,f)
 blob=base64.b64decode(a['blob']);sha=hashlib.sha256(blob).hexdigest();assert a['filename'].startswith(sha+'.')
 files=frappe.get_all('File',filters={'file_name':a['filename'],'is_private':0},fields=['name','file_url']);assert len(files)<=1
 if files:
  content=frappe.get_doc('File',files[0].name).get_content()
  if isinstance(content,str):content=content.encode()
  assert hashlib.sha256(content).hexdigest()==sha
  url=files[0].file_url
 else:url=save_file(a['filename'],blob,None,None,is_private=0).file_url
 frappe.db.commit();print(json.dumps({'message':{'file_url':url}}))
except Exception:frappe.db.rollback();raise
finally:frappe.destroy()
'''


def native_file(filename, blob, diagnostics):
    a = subprocess.run(['docker', 'exec', '-i', '-w', '/home/frappe/frappe-bench/sites',
                        'rootedops-full-test-erpnext-backend-1', '/home/frappe/frappe-bench/env/bin/python', '-c', FILE_NATIVE],
                       input=json.dumps({'filename': filename, 'blob': base64.b64encode(blob).decode()}),
                       text=True, capture_output=True)
    if a.returncode:
        private_write(diagnostics, {'stdout': a.stdout, 'stderr': a.stderr})
        raise RuntimeError('Native ERP media operation failed; private diagnostics retained')
    return json.loads(a.stdout)


def run(environment, batch, archive_only=False):
    target, private = guarded_environment(environment)
    work = private / 'catalog-expansion' / ('batch-' + str(batch)); work.mkdir(mode=0o700, parents=True, exist_ok=True)
    source_bytes = (SOURCE / 'public-products.json').read_bytes()
    source = json.loads(source_bytes)
    candidates = json.loads((SOURCE / 'batch-candidates.json').read_text())['batches'][batch-1] if batch else [
        {'source_key': r['source_key'], 'sku': r['content']['item'], 'category_ids': r['category_ids']}
        for r in json.loads((SOURCE / 'pilot-api-plan.json').read_text())['products']]
    keys = [r['source_key'] for r in candidates]
    selected = []
    for row in source['products']:
        if 'ecwid:95802503:product:' + str(row['id']) not in keys:
            continue
        if row.get('enabled') is not True or row.get('options') != [] or row.get('combinations') != []:
            raise ValueError('Review actual options/variations before simple-product import')
        row = dict(row, _combinations=row['combinations'])
        selected.append(row)
    if len(selected) != len(keys) or not 1 <= len(selected) <= 5:
        raise ValueError('Exact prepared batch identities required')
    for row in selected:
        candidate = next(r for r in candidates if r['source_key'].endswith(':' + str(row['id'])))
        if candidate['sku'] != row['sku'] or str(candidate['category_ids']) != str(row['categoryIds']):
            raise ValueError('Prepared identity/category drift')
    source_plan = plan({'store_id': '95802503', 'products': selected})
    if source_plan['errors']:
        raise ValueError(source_plan['errors'])
    private_write(work / 'plan.json', source_plan)
    urls = list(dict.fromkeys(g['source_url'] for r in source_plan['products'] for g in r['content']['gallery']))
    if any(urlsplit(u).hostname != CDN for u in urls):
        raise ValueError('Unreviewed original media host')
    media_dir = work / 'media'
    if (media_dir / 'manifest.json').exists():
        manifest = json.loads((media_dir / 'manifest.json').read_text())
        if {r['url'] for r in manifest} != set(urls):
            raise ValueError('Partial media archive; inspect and resume exact missing URLs')
    else:
        manifest = archive({'products': [{'originalImageUrl': u} for u in urls]}, media_dir, {CDN})
        if not urls:
            private_write(media_dir / 'manifest.json', [])
    if archive_only:
        print(json.dumps({'batch': batch, 'products': len(selected), 'original_urls_archived': len(manifest)})); return
    c = json.loads((private / 'wordpress-credentials.json').read_text())
    auth = 'Basic ' + base64.b64encode((c['username'] + ':' + c['application_password']).encode()).decode()
    upload_receipt = work / 'upload-receipt.json'
    existing = json.loads(upload_receipt.read_text()) if upload_receipt.exists() else {
        'scope': target['erp'] + '|' + target['shop'], 'blobs': {}}
    # Reconcile checksum-named Woo attachments before any retry, including an
    # interrupted prior response. The same source binary may serve several URLs.
    for row in manifest:
        found = api(target['shop'] + '/wp-json/wp/v2/media?' + urlencode({'search': row['sha256'], 'per_page': 100, 'context': 'edit'}), auth)
        found = [m for m in found if row['sha256'] in urlsplit(m['source_url']).path]
        if len(found) > 1:
            raise ValueError('Duplicate checksum attachments require explicit reconciliation')
        old = existing['blobs'].setdefault(row['sha256'], {})
        if found:
            if old.get('woocommerce_media_id') not in (None, found[0]['id']):
                raise ValueError('Media receipt ownership drift')
            old['woocommerce_media_id'] = found[0]['id']
        elif old.get('woocommerce_media_id'):
            raise ValueError('Receipted attachment missing')
    private_write(upload_receipt, existing)
    def request(url, authorization, body, headers):
        if url == target['erp'] + '/api/method/upload_file':
            mime = BytesParser(policy=policy.default).parsebytes(('Content-Type: ' + headers['Content-Type'] + '\r\n\r\n').encode() + body)
            part = next(p for p in mime.iter_parts() if p.get_filename())
            return native_file(part.get_filename(), part.get_payload(decode=True), work / 'media-error.json')
        return upload_request(url, authorization, body, headers)
    uploaded = upload(manifest, media_dir, upload_receipt, target['erp'], target['shop'], '', auth, request=request)
    private_write(work / 'uploaded-media.json', uploaded)
    checksums = {r['url']: r['sha256'] for r in uploaded}
    for r in source_plan['products']:
        seen, gallery = set(), []
        for image in r['content']['gallery']:
            sha = checksums[image['source_url']]
            if sha not in seen:
                seen.add(sha); gallery.append(image)
        r['content']['gallery'] = gallery
    categories = {str(r['id']): r for r in api(target['shop'] + '/wp-json/wc/v3/products/categories?per_page=100', auth)}
    for identity, name in [('18', 'Grow Kits and Mycology Supplies'), ('19', 'Gourmet Mushrooms')]:
        if categories[identity]['name'] != name:
            raise ValueError('Installed category identity drift')
    review = {'source_sha256': source_plan['source_sha256'], 'currency': 'USD', 'currency_confirmed': True,
              'selling_price_list': 'Ecwid Catalog Pilot USD', 'defer_tax_mapping': True, 'draft_only': True,
              'items': {r['content']['item']: {'item_code': r['content']['item'],
                         'item_group': 'Ecwid Catalog Migration Pilot', 'stock_uom': 'Nos'} for r in source_plan['products']},
              'categories': {'160277251': {'woocommerce_id': 18}, '160254004': {'woocommerce_id': 19}}, 'attributes': {}}
    private_write(work / 'review.json', review)
    compiled = compile_catalog(source_plan, review, uploaded)
    records_for_batch(compiled)
    private_write(work / 'compiled.json', compiled)
    private_write(work / 'source-lineage.json', {'public_source_sha256': hashlib.sha256(source_bytes).hexdigest(),
                                               'selected_source_keys': keys, 'tax_mapping_pending': True})
    print(json.dumps({'batch': batch, 'products': len(selected), 'media': len(uploaded),
                      'compiled': str(work / 'compiled.json'), 'sha256': hashlib.sha256((work / 'compiled.json').read_bytes()).hexdigest()}))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('environment', type=Path)
    p.add_argument('--batch', type=int, choices=range(0, 5), required=True,
                   help='1–4 prepared expansion batches; 0 prepares existing pilot gallery media only')
    p.add_argument('--archive-only', action='store_true')
    a = p.parse_args(); run(a.environment, a.batch, a.archive_only)
