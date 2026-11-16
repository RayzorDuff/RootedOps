"""Exact HTTPS origins for the authorized commerce staging environments."""
from urllib.parse import urlsplit


def staging_origin(value, service):
    if service not in ('erp', 'shop'):
        raise ValueError('Unknown staging service')
    p = urlsplit(value)
    allowed = {service+'-'+suffix+'.danks.store' for suffix in ('test', 'test2')}
    if (p.scheme != 'https' or p.hostname not in allowed or p.port not in (None, 443)
            or p.username or p.password or p.query or p.fragment or p.path not in ('', '/')):
        raise ValueError('Exact approved HTTPS staging origin required')
    return 'https://'+p.hostname


def staging_pair(erp, shop):
    erp, shop = staging_origin(erp, 'erp'), staging_origin(shop, 'shop')
    if erp.removeprefix('https://erp-') != shop.removeprefix('https://shop-'):
        raise ValueError('Mixed staging environments refused')
    return erp, shop


def customer_pair(erp, shop, production_erp_pilot=False):
    if production_erp_pilot is True:
        if (erp != 'https://erp.danks.store'
                or staging_origin(shop, 'shop') != 'https://shop-test.danks.store'):
            raise ValueError('Production ERP customer pilot requires the exact shared-Linode pair')
        return erp, 'https://shop-test.danks.store'
    return staging_pair(erp, shop)
