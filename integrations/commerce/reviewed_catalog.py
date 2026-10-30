"""Compile an explicitly reviewed Ecwid plan into ERP and WooCommerce payloads.

Pure transformation: never infers currency, tax accounts, variant identity or
remote media ownership. Missing review fails before any destination write.
"""
from copy import deepcopy
from decimal import Decimal, InvalidOperation
import hashlib
import json


def money(value):
    try:
        amount = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError('Invalid money') from exc
    if not amount.is_finite() or amount < 0:
        raise ValueError('Money must be finite and nonnegative')
    return format(amount, 'f')


def compile_catalog(plan, review, media_manifest=()):
    if plan.get('errors') or review.get('source_sha256') != plan['source_sha256']:
        raise ValueError('Review must bind the error-free source digest')
    currency = review['currency']
    if len(currency) != 3 or not currency.isalpha() or currency != currency.upper():
        raise ValueError('Explicit ISO currency required')
    if not review.get('currency_confirmed'):
        raise ValueError('Confirm source currency (CSV does not establish it)')
    blobs = {}
    for media in media_manifest:
        url = media['url']
        if url in blobs:
            raise ValueError('Ambiguous media manifest')
        blobs[url] = media
    records, codes = [], set()
    # Parents must precede variants, regardless of source product order.
    source = sorted(plan['products'], key=lambda p: bool(p['item'].get('parent_sku')))
    for product in source:
        sku = product['content']['item']
        r = review['items'][sku]
        code = r['item_code']
        if not code or code in codes:
            raise ValueError('ERP Item mappings must be unique')
        codes.add(code)
        content = deepcopy(product['content']); content['item'] = code
        item = {'item_code': code, 'item_name': content['public_title'],
                'item_group': r['item_group'], 'stock_uom': r['stock_uom']}
        wc = deepcopy(product['woocommerce'])
        # Publication remains a separate reviewed action.
        wc['status'] = 'draft'
        wc['categories'] = []
        for category in product['category_ids']:
            category_map = review['categories'][str(category)]
            wc['categories'].append({'id': int(category_map['woocommerce_id'])})
        tax = review['taxes'][r['tax_key']]
        if tax['woocommerce_status'] not in ('taxable', 'none', 'shipping'):
            raise ValueError('Unsupported Woo tax status')
        wc.update(tax_status=tax['woocommerce_status'], tax_class=tax['woocommerce_class'])
        if tax.get('erp_item_tax_template'):
            item['taxes'] = [{'item_tax_template': tax['erp_item_tax_template']}]
        elif not tax.get('reviewed_no_item_tax'):
            raise ValueError('Review ERP tax treatment explicitly')
        parent_sku = product['item'].get('parent_sku')
        is_template = bool(product['item'].get('has_variants'))
        attributes, woo_attributes = [], []
        if parent_sku:
            item['variant_of'] = review['items'][parent_sku]['item_code']
            options = product['variant_options']
            names = set()
            for option in options:
                name, value = option['name'], str(option['value'])
                if name in names:
                    raise ValueError('Duplicate variation attribute')
                names.add(name)
                approved = review['attributes'][name]
                if value not in approved['values']:
                    raise ValueError('Unreviewed variant value')
                attributes.append({'attribute': approved['erp_attribute'], 'attribute_value': value})
                woo_attributes.append({'name': approved['woocommerce_name'], 'option': value})
            expected = set(review['items'][parent_sku]['attributes'])
            if names != expected:
                raise ValueError('Variation must assign every reviewed parent attribute')
        elif is_template:
            item['has_variants'] = 1
            for name in r['attributes']:
                approved = review['attributes'][name]
                attributes.append({'attribute': approved['erp_attribute']})
                woo_attributes.append({'name': approved['woocommerce_name'], 'variation': True,
                                       'visible': True, 'options': approved['values']})
        if attributes:
            item['attributes'] = attributes
        gallery = []
        for image in content.get('gallery', []):
            media = blobs.get(image['source_url'])
            if not media or not media.get('erp_file_url') or not media.get('woocommerce_media_id'):
                raise ValueError('Archive and upload every image before catalog apply')
            if len(media['sha256']) != 64 or any(c not in '0123456789abcdef' for c in media['sha256']):
                raise ValueError('Invalid archived media checksum')
            gallery.append(dict(image, image=media['erp_file_url']))
        content['gallery'] = gallery
        wc['images'] = [{'id': int(blobs[i['source_url']]['woocommerce_media_id'])}
                        for i in product['content'].get('gallery', [])]
        price = None
        if not is_template:
            rate = money(product['price'])
            price = {'currency': currency, 'price_list': review['selling_price_list'], 'item_price_rate': rate}
            wc['regular_price'] = rate
        mapping = dict(product['mapping'], item=code)
        records.append({'source_key': product['source_key'], 'item': item, 'content': content,
                        'mapping': mapping, 'price': price, 'woocommerce': wc,
                        'variant_attributes': woo_attributes, 'parent_sku': parent_sku})
    return {'schema_version': 1, 'source_sha256': plan['source_sha256'], 'records': records,
            'review_sha256': hashlib.sha256(json.dumps(review, sort_keys=True).encode()).hexdigest()}
