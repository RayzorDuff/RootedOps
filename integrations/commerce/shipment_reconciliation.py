"""Project previously committed MP shipment quantities to a stock-neutral ERP receipt."""
import hmac
import json
from urllib.parse import urlsplit

from staging_origin import staging_pair


def reconcile_shipment(inventory, erp, key, reference, secret):
    provider, site, order_id = key
    staging_pair(erp.base, 'https://' + site)
    if provider != 'woocommerce' or not reference or not isinstance(secret, str) or len(secret) < 32:
        raise ValueError('Reviewed movement, staging identity and private proof key required')
    erp_site = urlsplit(erp.base).hostname
    with inventory.connect() as db:
        rows = db.execute("""SELECT l.sales_order, p.line_id, x.value->>'erp_item_code', count(*)
               FROM public.mp_commerce_shipments s
               JOIN public.mp_commerce_shipped_products p USING(provider, site_key, movement_reference, external_order_id)
               JOIN public.mp_commerce_orders o USING(provider, site_key, external_order_id)
               JOIN public.mp_commerce_erp_links l USING(provider, site_key, external_order_id)
               CROSS JOIN LATERAL jsonb_array_elements(o.snapshot->'lines') x(value)
               WHERE s.provider=%s AND s.site_key=%s AND s.external_order_id=%s
                 AND s.movement_reference=%s AND l.erp_site=%s
                 AND l.sales_invoice IS NOT NULL AND l.payment_entry IS NOT NULL
                 AND p.line_id=x.value->>'line_id'
               GROUP BY l.sales_order,p.line_id,x.value->>'erp_item_code'
               ORDER BY p.line_id""", (*key, reference, erp_site)).fetchall()
    if not rows or len({row[0] for row in rows}) != 1:
        raise ValueError('Committed shipment and matching linked ERP sale required')
    packet = dict(provider=provider, site_key=site, external_order_id=order_id, reference=reference,
                  sales_order=rows[0][0], lines=[dict(line_id=row[1], item_code=row[2], quantity=row[3])
                                                 for row in rows])
    signature = hmac.digest(secret.encode(), json.dumps(packet, sort_keys=True,
                            separators=(',', ':')).encode(), 'sha256').hex()
    return erp.request(erp.base + '/api/method/rootedops_commerce.fulfillment.acknowledge_shipment',
                       erp.authorization, 'POST',
                       {'payload': json.dumps(packet), 'signature': signature})['message']
