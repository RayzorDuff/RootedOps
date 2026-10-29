"""Draft-only WooCommerce projection adapter; no order/payment/stock side effects.

All target IDs are resolved via exact SKU plus durable source metadata. No
updates are made to preexisting unowned products. Variants require reviewed
WooCommerce attribute assignments and parent target ID.
"""
from ecwid_migrate import api
from urllib.parse import urlencode


def draft_payload(record, parent_id=None, attributes=None):
    body = dict(record['woocommerce'])
    if record['item'].get('parent_sku'):
        if not parent_id or not attributes:
            raise ValueError('Reviewed parent ID and WooCommerce variant attributes required')
        # Variations inherit name/description/gallery from the parent. The full
        # source remains in ERP and the plan, rather than dropping it silently.
        body = {k:v for k,v in body.items() if k in ('sku','description','meta_data')}
        body['attributes'] = attributes
        if record['woocommerce'].get('images'):
            body['image'] = record['woocommerce']['images'][0]
    elif record['item'].get('has_variants'):
        if not attributes:
            raise ValueError('Reviewed WooCommerce parent attributes required')
        body['type'] = 'variable';body['attributes'] = attributes
    else:
        body['type'] = 'simple'
    return body


def upsert_draft(base_url, authorization, record, parent_id=None, attributes=None, request=api):
    from urllib.parse import urlsplit, quote
    if urlsplit(base_url).hostname != 'shop-test.danks.store':
        raise ValueError('Adapter restricted to shop-test.danks.store')
    body = draft_payload(record, parent_id, attributes)
    root = base_url.rstrip('/') + '/wp-json/wc/v3/'
    resource = f'products/{int(parent_id)}/variations' if record['item'].get('parent_sku') else 'products'
    matches = request(root + resource + '?' + urlencode({'sku':body['sku'],'per_page':100}), authorization)
    matches = [r for r in matches if r.get('sku') == body['sku']]
    if len(matches) > 1:
        raise ValueError('Ambiguous WooCommerce SKU')
    if matches:
        old = matches[0]
        metadata = {m['key']:m['value'] for m in old.get('meta_data',[])}
        if metadata.get('_rootedops_source_key') != record['source_key']:
            raise ValueError('Existing WooCommerce SKU not owned by migration')
        if old.get('status') not in ('draft', None):
            raise ValueError('Refusing to overwrite a published product')
        return request(root + resource + '/' + str(old['id']), authorization, 'PUT', body)
    return request(root + resource, authorization, 'POST', body)
