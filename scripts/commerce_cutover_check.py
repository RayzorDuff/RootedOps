#!/usr/bin/env python3
"""Read-only opening stock and redirect checks for the Dank storefront."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
import json
import os
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import build_opener, HTTPRedirectHandler, Request
from xml.etree import ElementTree

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'integrations/commerce'))
from ecwid_migrate import api

SHOPS = ('danks.store', 'shop-test.danks.store')
QR = 'qr.danks.store'


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def request(url):
    try:
        response = build_opener(NoRedirect).open(Request(url, method='HEAD'), timeout=10)
    except HTTPError as exc:
        response = exc
    with response:
        return response.code, response.headers.get('Location')


def walk(url, host, get=request):
    chain = []
    for _ in range(8):
        parsed = urlsplit(url)
        if (parsed.scheme != 'https' or parsed.netloc not in (host, QR)
                or (parsed.netloc == QR and chain)):
            raise ValueError(f'Unexpected redirect origin: {parsed.netloc}')
        status, location = get(url)
        chain.append((url, status))
        if status not in (301, 302, 303, 307, 308):
            return chain
        if not location:
            raise ValueError('Redirect Location missing')
        url = urljoin(url, location)
    raise ValueError('Redirect loop or excessive hops')


def paths(sitemap):
    found = []
    for row in ElementTree.parse(sitemap).getroot().findall('{*}url/{*}loc'):
        url = urlsplit(row.text.strip())
        if url.hostname not in ('danks.store', 'www.danks.store', 'shop-test.danks.store'):
            raise ValueError('Sitemap contains an unreviewed origin')
        if url.path.startswith('/products/') or url.path.rstrip('/') == '/products':
            found.append(url.path)
    if len(found) != 42 or len(set(found)) != len(found):
        raise ValueError(f'Use the saved 42-path Ecwid sitemap, got {len(found)} legacy paths')
    return found


def expected_rows(source):
    entries = {}
    for row in csv.DictReader(source):
        path = row['path']
        if path in entries or row['disposition'] not in ('redirect', 'retired', 'decision'):
            raise ValueError('Duplicate path or unsupported disposition')
        target = row['final_path']
        if row['disposition'] == 'redirect' and (not target.startswith('/') or target.startswith('//')):
            raise ValueError('Expected final path must be an exact local Woo path')
        entries[path] = row
    return entries


def redirects(host, sitemap, expected, qr, code):
    urls = paths(sitemap)
    plan = expected_rows(expected) if expected else None
    if plan is not None and set(plan) != set(urls):
        raise ValueError('Reviewed manifest and saved sitemap must match exactly')
    if plan is None and host != 'shop-test.danks.store':
        raise ValueError('Review staging destinations before testing the final hostname')
    def probe(path):
        for attempt in range(2):
            try:
                return walk('https://' + host + path, host), None
            except (URLError, TimeoutError, ValueError) as exc:
                error = str(exc)
                if isinstance(exc, ValueError):
                    break
        return None, error

    failures, outcomes = 0, {200: 0, 404: 0}
    writer = csv.writer(sys.stdout, lineterminator='\n')
    writer.writerow(('path', 'disposition', 'final_path'))
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(probe, urls))
    for path, (chain, error) in zip(urls, results):
        if error:
            print(f'REVIEW {path} {error}', file=sys.stderr)
            failures += 1
            continue
        final, status = chain[-1]
        final_path = urlsplit(final).path
        matched = len(chain) > 1 and chain[0][1] == code and status == 200
        if plan is not None:
            row = plan[path]
            matched = (matched and final_path == row['final_path']
                       if row['disposition'] == 'redirect' else len(chain) == 1 and status == 404)
        else:
            matched = matched or len(chain) == 1 and status == 404
        if not matched:
            failures += 1
            print(f'REVIEW {path} {chain}', file=sys.stderr)
        outcomes[status] = outcomes.get(status, 0) + 1
        label = (plan[path]['disposition'] if plan else
                 'decision' if path.rstrip('/').endswith('-c160255005') else
                 'retired' if status == 404 else 'redirect')
        writer.writerow((path, label, final_path if status == 200 else ''))
    if plan is None and outcomes != {200: 29, 404: 13}:
        failures += 1
    if qr:
        for row in csv.DictReader(qr):
            url = row['url']
            if urlsplit(url).netloc != QR:
                raise ValueError('Use a qr.danks.store label URL')
            chain = walk(url, host)
            target, status = chain[-1]
            if (status != 200 or urlsplit(target).netloc != host
                    or urlsplit(target).path != row['final_path']):
                failures += 1
                print(f'QR REVIEW {chain}', file=sys.stderr)
    elif host == 'danks.store':
        failures += 1
        print('Supply the QR label sample CSV (url,final_path).', file=sys.stderr)
    print(f'Outcomes {outcomes}, failures {failures}', file=sys.stderr)
    return 1 if failures else 0


def stock(host, source, authorization, fetch=api):
    seen, ids, mp_ids, active_pools, failures = set(), set(), set(), set(), 0
    for row in csv.DictReader(source):
        woo_id, parent = row['woo_id'], row['parent_woo_id']
        mp_id = row['mp_id']
        if (not woo_id.isdecimal() or int(woo_id) <= 0 or parent and
                (not parent.isdecimal() or int(parent) <= 0 or parent == woo_id)
                or not mp_id.isdecimal() or int(mp_id) <= 0
                or not row['sku'] or not row['source_key'] or not row['pool_key']
                or row['sku'] in seen or woo_id in ids or mp_id in mp_ids):
            raise ValueError('Exact unique Woo, SKU, ownership and MP mapping required')
        seen.add(row['sku'])
        ids.add(woo_id)
        mp_ids.add(mp_id)
        root = f'https://{host}/wp-json/wc/v3/products/'
        product = fetch(root + (parent + '/variations/' if parent else '') + woo_id, authorization)
        owner = fetch(root + parent, authorization) if parent else product
        meta = [m['value'] for m in owner.get('meta_data', []) if m['key'] == '_rootedops_source_key']
        qty = int(row['mp_available'])
        pool_key = row['pool_key']
        if qty > 0 and pool_key in active_pools:
            raise ValueError('Multiple positive Woo stock listings share one MP pool')
        if qty > 0:
            active_pools.add(pool_key)
        correct = (qty >= 0 and meta == [row['source_key']]
                   and product.get('id') == int(woo_id) and product.get('sku') == row['sku']
                   and owner.get('id') == int(parent or woo_id)
                   and owner.get('type') == ('variable' if parent else 'simple')
                   and owner.get('status') == 'publish' and product.get('status') == 'publish'
                   and product.get('manage_stock') is True and product.get('backorders') == 'no'
                   and type(product.get('stock_quantity')) is int and product['stock_quantity'] == qty)
        failures += not correct
        print(json.dumps(dict(sku=row['sku'], woo_id=woo_id, mp_id=mp_id, expected=qty,
                              observed=product.get('stock_quantity'), result='ok' if correct else 'review')))
    return 1 if failures or not seen else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('redirects', 'stock'))
    parser.add_argument('input', type=Path)
    parser.add_argument('--host', choices=SHOPS, default='danks.store')
    parser.add_argument('--expected', type=argparse.FileType())
    parser.add_argument('--qr', type=argparse.FileType())
    parser.add_argument('--redirect-status', type=int, choices=(302, 301), default=302)
    args = parser.parse_args()
    if args.mode == 'redirects':
        return redirects(args.host, args.input, args.expected, args.qr, args.redirect_status)
    with args.input.open() as stream:
        return stock(args.host, stream, os.environ['WC_AUTHORIZATION'])


if __name__ == '__main__':
    raise SystemExit(main())
