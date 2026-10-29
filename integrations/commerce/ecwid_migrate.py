#!/usr/bin/env python3
"""Offline-first Ecwid extraction, reconciliation and staged ERP import.

No writes to Ecwid. Never creates ERP invoices, payments or operational stock.
Source JSON is retained verbatim; products are planned as draft channel projections.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
from urllib.parse import urlencode, quote, urlsplit
from urllib.request import Request, urlopen


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def api(url, token, method='GET', payload=None):
    if urlsplit(url).scheme != 'https':
        raise ValueError('API requires HTTPS')
    # Never forward credentials to an unexpected redirect destination.
    from urllib.request import HTTPRedirectHandler, build_opener
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            raise ValueError('API redirect rejected')
    req = Request(url, data=None if payload is None else canonical(payload).encode(),
                  headers={'Authorization': token, 'Content-Type': 'application/json'}, method=method)
    with build_opener(NoRedirect).open(req, timeout=60) as response:
        return json.load(response)


def pages(get, resource):
    result = []
    offset = 0
    expected = None
    while True:
        page = get(resource + '?' + urlencode({'offset': offset, 'limit': 100}))
        if isinstance(page, list):
            return page  # Ecwid combinations endpoint returns an array.
        if expected is None:
            expected = page['total']
        if page['total'] != expected:
            raise ValueError('Source changed during export; retry with writes paused')
        rows = page['items']
        result.extend(rows)
        offset += len(rows)
        if offset >= expected:
            break
        if not rows:
            raise ValueError('Incomplete pagination')
    if len(result) != expected or len({str(x['id']) for x in result}) != expected:
        raise ValueError('Incomplete or duplicate source IDs')
    return result


def extract(store_id, token):
    if not re.fullmatch(r'\d+', store_id):
        raise ValueError('Store ID must be numeric')
    root = 'https://app.ecwid.com/api/v3/' + store_id + '/'
    get = lambda path: api(root + path, 'Bearer ' + token)
    data = {'schema_version': 1, 'store_id': store_id}
    for kind in ('products', 'customers', 'orders', 'categories'):
        data[kind] = pages(get, kind)
    data['profile'] = get('profile')
    for product in data['products']:
        product['_combinations'] = pages(get, f"products/{product['id']}/combinations")
    return data


def plan(data):
    store = str(data['store_id'])
    records, products, errors = [], [], []
    skus, identities = set(), set()
    for kind in ('customers', 'orders', 'categories'):
        singular = {'customers': 'customer', 'orders': 'order', 'categories': 'category'}[kind]
        for row in data.get(kind, []):
            key = f"ecwid:{store}:{singular}:{row['id']}"
            if key in identities:
                errors.append('Duplicate identity: ' + key)
            identities.add(key)
            records.append({'doctype': 'Commerce Source Archive', 'source_key': key,
                            'record_type': singular, 'payload': canonical(row)})
    records.append({'doctype': 'Commerce Source Archive', 'source_key': f'ecwid:{store}:profile:initial',
                    'record_type': 'profile', 'payload': canonical(data.get('profile', {}))})
    for row in data.get('products', []):
        variants = row.get('_combinations', [])
        for variant in [None] + variants:
            source = variant if variant is not None else row
            sku = str(source.get('sku') or '').strip()
            key = f"ecwid:{store}:product:{row['id']}" + (f":variation:{source['id']}" if variant is not None else '')
            if key in identities:
                errors.append('Duplicate identity: ' + key)
            identities.add(key)
            if not sku:
                errors.append('Missing SKU: ' + key)
                continue
            if sku in skus:
                errors.append('Duplicate SKU: ' + sku)
            skus.add(sku)
            images = []
            if row.get('imageUrl'):
                images.append(row['imageUrl'])
            images += [i['url'] for i in row.get('galleryImages', []) if i.get('url')]
            if variant is not None and source.get('imageUrl'):
                images.insert(0, source['imageUrl'])
            images = list(dict.fromkeys(images))
            content = {'doctype': 'Commercial Product Content', 'item': sku,
                'public_title': row.get('name') or sku, 'publication_status': 'Draft',
                'short_description': row.get('shortDescription', ''),
                'full_description': row.get('description', ''),
                'seo_title': row.get('seoTitle', ''), 'seo_description': row.get('seoDescription', ''),
                'gallery': [{'image': u, 'source_url': u} for u in images],
                'source_key': key, 'source_payload': canonical({'product': row, 'variation': variant})}
            wc = {'name': content['public_title'], 'sku': sku, 'status': 'draft',
                  'description': content['full_description'], 'short_description': content['short_description'],
                  'images': [{'src': u} for u in images],
                  'meta_data': [{'key': '_rootedops_source_key', 'value': key},
                                {'key': '_rootedops_seo_title', 'value': content['seo_title']},
                                {'key': '_rootedops_seo_description', 'value': content['seo_description']}]}
            products.append({'source_key': key, 'content': content, 'woocommerce': wc,
                'item': {'item_code': sku, 'item_name': content['public_title'],
                         'has_variants': bool(variants) if variant is None else False,
                         'parent_sku': row.get('sku') if variant is not None else None},
                'mapping': {'provider': 'ecwid', 'site_key': store, 'item': sku,
                            'external_product_id': str(row['id']),
                            'external_variation_id': str(source['id']) if variant is not None else '',
                            'external_sku': sku, 'sync_enabled': 0},
                'price': source.get('price', row.get('price')),
                'variant_options': source.get('options', []),
                'category_ids': row.get('categoryIds', []),
                'source_enabled': row.get('enabled', False)})
    return {'schema_version': 1, 'source_sha256': digest(data), 'products': products,
            'archives': records, 'errors': errors,
            'counts': {k: len(data.get(k, [])) for k in ('products', 'customers', 'orders', 'categories')},
            'limitations': ['ERP Items/variant attributes, price lists, currency and tax mappings require review.',
                'WooCommerce variable products and variants require an approved attribute mapping before publication.',
                'Customer/order history is archived only: no live customers, orders, invoices, fulfillment or emails.',
                'Image URLs are references, not an offline media backup; archive binaries before retiring Ecwid.',
                'SEO metadata requires a storefront SEO adapter; private meta fields alone do not publish SEO.']}


def apply_erp(document, base, token, item_map):
    """Repeatable inserts; reject drift rather than silently overwrite reviewed edits."""
    if document['errors']:
        raise ValueError('Resolve reconciliation errors before import')
    root = base.rstrip('/') + '/api/resource/'
    def ensure(doc):
        kind = doc['doctype']
        field = 'item' if kind == 'Commercial Product Content' else 'source_key'
        filters = [[kind, field, '=', doc[field]]]
        found = api(root + quote(kind) + '?' + urlencode({'filters': canonical(filters), 'fields': '["name"]'}), token)['data']
        if len(found) > 1:
            raise ValueError('Ambiguous target identity')
        if found:
            existing = api(root + quote(kind) + '/' + quote(found[0]['name'], safe=''), token)['data']
            fields = ('source_payload',) if kind == 'Commercial Product Content' else ('payload',)
            if any(existing.get(k) != doc[k] for k in fields):
                raise ValueError('Source changed; explicit reconciliation required: ' + doc[field])
            return
        api(root + quote(kind), token, 'POST', doc)
    for product in document['products']:
        content = dict(product['content'])
        if content['item'] not in item_map:
            raise ValueError('Missing reviewed ERP Item mapping: ' + content['item'])
    for product in document['products']:
        content = dict(product['content']);content['item'] = item_map[content['item']]
        ensure(content)
    for record in document['archives']:
        ensure(record)


def private_write(path, value):
    path = Path(path)
    # Atomic, restrictive write even when replacing an older file.
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as f:
        os.chmod(f.name, 0o600)
        json.dump(value, f, indent=2, ensure_ascii=False)
        temp = f.name
    os.replace(temp, path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    ex = sub.add_parser('export');ex.add_argument('--store-id', required=True);ex.add_argument('--output', required=True)
    pl = sub.add_parser('plan');pl.add_argument('source');pl.add_argument('--output', required=True)
    im = sub.add_parser('apply-erp');im.add_argument('plan');im.add_argument('--base-url',required=True);im.add_argument('--item-map',required=True)
    im.add_argument('--allow-staging-write', action='store_true')
    args = parser.parse_args()
    if args.command == 'export':
        private_write(args.output, extract(args.store_id, os.environ['ECWID_TOKEN']))
    elif args.command == 'plan':
        result = plan(json.loads(Path(args.source).read_text()));private_write(args.output, result)
        print(json.dumps({'counts': result['counts'], 'errors': result['errors'], 'limitations': result['limitations']}))
        return 1 if result['errors'] else 0
    else:
        if not args.allow_staging_write or urlsplit(args.base_url).hostname != 'erp-test.danks.store':
            parser.error('Writes require --allow-staging-write and erp-test.danks.store')
        apply_erp(json.loads(Path(args.plan).read_text()), args.base_url, os.environ['ERP_AUTHORIZATION'], json.loads(Path(args.item_map).read_text()))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
