"""ERP-side admission for the owner-approved production orders."""
from datetime import datetime

import frappe

ERP_SITE = 'erp.danks.store'
WOO_SITE = 'danks.store'


def authorize(event, *, capture=False):
    if getattr(getattr(frappe, 'local', None), 'site', None) != ERP_SITE:
        return False
    config = frappe.conf.get('commerce_live_order') or {}
    if (config.get('enabled') is not True or event.get('provider') != 'woocommerce'
            or event.get('site_key') != WOO_SITE):
        raise ValueError('Production order is outside the approved launch scope')
    order_id = event.get('external_order_id')
    if config.get('mode', 'pilot') == 'review':
        approved_orders = config.get('approved_orders')
        approval = approved_orders.get(order_id) if isinstance(approved_orders, dict) else None
        if not isinstance(approval, dict) or approval.get('enabled') is not True:
            raise ValueError('Woo order needs individual ERP approval')
    elif config.get('mode', 'pilot') == 'pilot' and config.get('woo_order_id') and str(config['woo_order_id']) == order_id:
        approval = config
    else:
        raise ValueError('Production order is outside the approved launch scope')
    if 'source_created_gmt' in event:
        fmt = '%Y-%m-%dT%H:%M:%S'
        if datetime.strptime(event['source_created_gmt'], fmt) < datetime.strptime(config['not_before_gmt'], fmt):
            raise ValueError('Order predates the approved production window')
    if capture and (approval.get('capture_enabled') is not True or not approval.get('clover_charge_id')
                    or event.get('payment_id') != approval['clover_charge_id']):
        raise ValueError('Production Clover charge is outside the approved launch scope')
    return True
