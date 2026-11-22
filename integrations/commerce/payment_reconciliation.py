"""Read a Clover sandbox capture and converge ERP and MP using durable identities."""
from datetime import date
import hmac
import json
from urllib.parse import urlsplit

from staging_origin import order_pair


def reconcile_capture(inbox, inventory, erp, clover, key, posting_date, secret, *, production=False):
    provider, site, order_id = key
    order_pair(erp.base, 'https://' + site, production=production)
    if provider != 'woocommerce' or not isinstance(secret, str) or len(secret) < 32:
        raise ValueError('Staging Woo identity and private evidence key required')
    event, number = inbox.completed_woo_payment_source(key)
    if event.get('refunds'):
        clover.evidence(event, reviewed_order={'id': order_id, 'number': number})
        return {'status': 'refund_review'}
    if event['status'] not in ('processing', 'completed'):
        return {'status': 'awaiting_paid_woo_snapshot'}
    evidence = clover.evidence(event, reviewed_order={'id': order_id, 'number': number})
    packet = dict(evidence, provider=provider, posting_date=date.fromisoformat(posting_date).isoformat())
    signature = hmac.digest(secret.encode(), json.dumps(packet, sort_keys=True,
                            separators=(',', ':')).encode(), 'sha256').hex()
    result = erp.request(erp.base + '/api/method/rootedops_commerce.clover_payment.reconcile_capture',
                         erp.authorization, 'POST',
                         {'payload': json.dumps(packet), 'signature': signature})['message']
    with inventory.connect() as db:
        db.execute('SELECT public.mp_commerce_match_payment(%s::jsonb)', (json.dumps(packet),))
        link = dict(provider=provider, site_key=site, external_order_id=order_id,
                    erp_site=urlsplit(erp.base).hostname, **result)
        db.execute('SELECT public.mp_commerce_link_erp(%s::jsonb)', (json.dumps(link),))
        db.execute('SELECT public.mp_commerce_confirm_reservation(%s,%s,%s)', key)
    return {'status': 'confirmed', **result}
