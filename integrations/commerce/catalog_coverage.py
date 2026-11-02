"""Reconcile immutable CSV identities with later API data and destination receipts.

No destination writes; public disabled placeholders never erase CSV identities.
Only installed read-back receipts establish migrated coverage.
"""
from collections import Counter
from decimal import Decimal


PILOT_IDS = {'610274980', '610274742', '711334880'}
APPROVED_CATEGORIES = {'Grow Kits and Mycology Supplies', 'Gourmet Mushrooms'}


def reconcile(rows, api_products=(), verified=()):
    ids, skus = set(), set()
    api_by_id = {str(p['id']): p for p in api_products}
    if len(api_by_id) != len(api_products):
        raise ValueError('Duplicate API identity')
    receipts = {}
    for r in verified:
        identity = str(r['ecwid_product_id'])
        if identity in receipts:
            raise ValueError('Duplicate installed receipt identity')
        if r.get('installed_verified') is not True or not r.get('woo_id') or not r.get('erp_item'):
            raise ValueError('Installed read-back evidence required for migrated status')
        receipts[identity] = r
    records = []
    for row in rows:
        identity, sku = row['product_id'].strip(), row['sku'].strip()
        if not identity or identity in ids or not sku or sku.casefold() in skus:
            raise ValueError('Missing/duplicate CSV identity or SKU')
        ids.add(identity); skus.add(sku.casefold())
        enabled = row.get('enabled', '').strip().lower() == 'yes'
        categories = [row[k] for k in ('category1', 'category2', 'category3') if row.get(k)]
        api = api_by_id.get(identity)
        discrepancies = []
        if api and api.get('sku'):
            if api['sku'] != sku:
                discrepancies.append('API SKU differs from immutable CSV')
            if Decimal(str(api['price'])) != Decimal(row['price']):
                discrepancies.append('API price differs from CSV; review current source')
            if api.get('enabled') is not enabled:
                discrepancies.append('API enabled state differs from CSV')
        elif api is not None:
            discrepancies.append('API placeholder; preserve original CSV fields')
        receipt = receipts.get(identity)
        if receipt:
            if receipt['erp_item'] != sku:
                raise ValueError('Installed receipt SKU drift')
            status, reason = 'migrated', 'Installed ERP and Woo read-back receipt'
        elif not enabled:
            status, reason = 'excluded', 'Disabled source; archive/history only, no sellable recreation'
        elif 'Disabled' in categories:
            status, reason = 'pending', 'Enabled in Disabled category; owner review required'
        elif not categories:
            status, reason = 'pending', 'Uncategorized; owner review required'
        elif not set(categories).issubset(APPROVED_CATEGORIES):
            status, reason = 'pending', 'Unreviewed category path'
        elif identity in PILOT_IDS:
            status, reason = 'pending', 'Pilot identity; inspect installed receipts before replay'
        else:
            status, reason = 'pending', 'Prepared category-appropriate draft candidate'
        records.append({'ecwid_product_id': identity, 'sku': sku, 'title': row['name'],
                        'source_enabled': enabled, 'categories': categories, 'status': status,
                        'reason': reason, 'csv_price': row['price'], 'source_tax_class': row.get('taxClassCode'),
                        'source_gaps': [k for k in ('image', 'seo_title', 'seo_description') if not row.get(k)],
                        'discrepancies': discrepancies,
                        'options_verified': api is not None and 'options' in api,
                        'options': api.get('options') if api is not None else None,
                        'combinations_verified': api is not None and '_combinations' in api,
                        'combinations': len(api['_combinations']) if api is not None and '_combinations' in api else None,
                        'destination': receipt})
    if set(receipts) - ids:
        raise ValueError('Installed receipt absent from original export')
    candidates = [r['ecwid_product_id'] for r in records
                  if r['reason'] == 'Prepared category-appropriate draft candidate' and not r['discrepancies']]
    return {'counts': dict(Counter(r['status'] for r in records)),
            'enabled': sum(r['source_enabled'] for r in records),
            'disabled': sum(not r['source_enabled'] for r in records),
            'records': records, 'candidate_batches': [candidates[i:i+5] for i in range(0, len(candidates), 5)],
            'api_only_ids': sorted(set(api_by_id) - ids),
            'limitations': ['CSV options/gallery completeness unknown without API evidence.',
                            'Tax class labels do not establish destination rates or exemptions.',
                            'Prepared candidates are not installed migration evidence.']}


if __name__ == '__main__':
    import argparse
    import hashlib
    import json
    from pathlib import Path
    from ecwid_csv import read_rows
    from ecwid_migrate import private_write
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('csv', type=Path)
    p.add_argument('--api-products', type=Path, help='Optional JSON array of later API records')
    p.add_argument('--verified', type=Path, help='Optional JSON array of installed destination receipts')
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    result = reconcile(read_rows(a.csv, {'product_id', 'sku', 'price', 'name'}),
                       json.loads(a.api_products.read_text()) if a.api_products else [],
                       json.loads(a.verified.read_text()) if a.verified else [])
    result['csv_sha256'] = hashlib.sha256(a.csv.read_bytes()).hexdigest()
    private_write(a.output, result)
    print(json.dumps({k: result[k] for k in ('counts', 'enabled', 'disabled', 'csv_sha256')}))
