"""ERP-side admission for the exact, owner-approved first production order."""
from datetime import datetime

import frappe

ERP_SITE = 'erp.danks.store'
WOO_SITE = 'danks.store'


def authorize(event, *, capture=False):
    if getattr(getattr(frappe, 'local', None), 'site', None) != ERP_SITE:
        return False
    config = frappe.conf.get('commerce_live_order') or {}
    if (config.get('enabled') is not True or event.get('provider') != 'woocommerce'
            or event.get('site_key') != WOO_SITE or not config.get('woo_order_id')
            or str(config['woo_order_id']) != event.get('external_order_id')):
        raise ValueError('Production order is outside the approved launch scope')
    if 'source_created_gmt' in event:
        fmt = '%Y-%m-%dT%H:%M:%S'
        if datetime.strptime(event['source_created_gmt'], fmt) < datetime.strptime(config['not_before_gmt'], fmt):
            raise ValueError('Order predates the approved production window')
    if capture and (config.get('capture_enabled') is not True or not config.get('clover_charge_id')
                    or event.get('payment_id') != config['clover_charge_id']):
        raise ValueError('Production Clover charge is outside the approved launch scope')
    return True
