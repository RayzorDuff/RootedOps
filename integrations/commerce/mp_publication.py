"""Retry committed MP dispatches independently and publish reservation-aware stock."""
import json
import os
from shipment_reconciliation import reconcile_shipment


def woo_request(origin, authorization, method, path, payload=None):
    import subprocess
    if origin not in ('https://shop-test.danks.store', 'https://danks.store', 'https://dankmushrooms.net'):
        raise ValueError('Exact installed Woo origin required')
    if any(ord(c) < 32 for c in authorization):
        raise ValueError('Invalid authorization header')
    argv = ['curl', '--disable', '--config', '-', '--silent', '--max-time', '60',
            '--proto', '=https', '--header', 'Content-Type: application/json', '-X', method]
    if payload is not None:
        argv += ['--data-binary', json.dumps(payload)]
    argv += ['--write-out', '\n%{http_code}', origin + '/wp-json/rootedops/v1' + path]
    result = subprocess.run(argv, input='header = ' + json.dumps('Authorization: ' + authorization) + '\n',
                            text=True, capture_output=True)
    body, _, code = result.stdout.rpartition('\n')
    if result.returncode or code != '200':
        raise RuntimeError('Woo projection rejected or unavailable')
    return json.loads(body)


def deliver_dispatches(mp, erp, config, request=woo_request):
    """Use a session lock so two timers cannot project the same Woo movement together."""
    with mp.connect() as db:
        if not db.execute('SELECT pg_try_advisory_lock(520056)').fetchone()[0]:
            return []
        try:
            rows = db.execute("""SELECT d.provider,d.site_key,k.external_order_id,d.movement_reference,
                        d.target,k.tracking
                FROM public.mp_commerce_shipment_delivery d JOIN public.mp_commerce_packages k
                ON (d.provider,d.site_key,d.movement_reference)=(k.provider,k.site_key,k.reference)
                WHERE d.delivered_at IS NULL ORDER BY d.attempts,k.created_at,d.target LIMIT 100""").fetchall()
            outcomes = []
            for provider, site, order_id, reference, target, tracking in rows:
                key = (provider, site, order_id)
                if site != config.get('site_key', 'danks.store'):
                    continue
                if config.get('mode', 'pilot') == 'pilot' and order_id != str(config['woo_order_id']):
                    continue
                try:
                    if target == 'erp':
                        reconcile_shipment(mp, erp, key, reference,
                                           os.environ['COMMERCE_SHIPMENT_EVIDENCE_KEY'], production=True)
                    else:
                        tracking = db.execute("""SELECT tracking FROM public.mp_commerce_packages
                            WHERE provider=%s AND site_key=%s AND reference=%s FOR UPDATE""",
                                              (provider, site, reference)).fetchone()[0]
                        lines = db.execute("""SELECT line_id,count(*) FROM public.mp_commerce_shipped_units
                            WHERE provider=%s AND site_key=%s AND movement_reference=%s
                            GROUP BY line_id ORDER BY line_id""", (provider, site, reference)).fetchall()
                        request(config['woo_origin'], os.environ['WOO_MP_AUTHORIZATION'], 'POST',
                                f'/orders/{order_id}/shipments', dict(reference=reference,
                                lines=[dict(line_id=line, quantity=qty) for line, qty in lines], tracking=tracking))
                    error = None
                except Exception:
                    error = 'target_error'
                db.execute("""UPDATE public.mp_commerce_shipment_delivery SET attempts=attempts+1,
                    last_error=%s,delivered_at=CASE WHEN %s IS NULL THEN now() ELSE NULL END
                    WHERE provider=%s AND site_key=%s AND movement_reference=%s AND target=%s""",
                           (error, error, provider, site, reference, target))
                db.commit()
                outcomes.append(dict(order_id=order_id, target=target, status=error or 'delivered'))
            return outcomes
        finally:
            db.execute('SELECT pg_advisory_unlock(520056)')


def inventory_snapshot(mp, mappings, site):
    """Snapshot both free stock and the holds/shipments represented in each Woo line."""
    with mp.connect() as db:
        db.execute('SELECT pg_advisory_xact_lock(520052)')
        revision = db.execute("SELECT nextval('public.mp_commerce_inventory_revision')").fetchone()[0]
        products, pools = [], set()
        for mapping in mappings:
            ecommerce_id = mapping['ecommerce_id']
            row = db.execute("""SELECT c.item_id,c.strain_id,i.available_quantity,c.provider,c.site_key,
                    c.external_product_id,c.external_variation_id,c.external_sku
                FROM public.mp_ecommerce_catalog_inventory() c JOIN public.mp_commerce_inventory() i
                USING(ecommerce_id) WHERE c.ecommerce_id=%s""", (ecommerce_id,)).fetchone()
            if not row or row[3:5] != ('woocommerce', site):
                raise ValueError('Exact MP Woo mapping required')
            pool = row[:2]
            if pool in pools:
                raise ValueError('Multiple published Woo listings share physical inventory')
            pools.add(pool)
            woo_id = row[5] if row[6] in (None, '', '0') else row[6]
            if str(mapping['woo_id']) != str(woo_id) or mapping['sku'] != row[7]:
                raise ValueError('Woo target identity differs from MP')
            represented = db.execute("""SELECT external_order_id,line_id,sum(quantity)::bigint FROM (
                SELECT external_order_id,line_id,quantity FROM public.mp_commerce_reservations
                 WHERE provider='woocommerce' AND site_key=%s AND ecommerce_id=%s
                UNION ALL
                SELECT p.external_order_id,p.line_id,count(*) FROM public.mp_commerce_shipped_units p
                 JOIN public.mp_commerce_orders o USING(provider,site_key,external_order_id)
                 CROSS JOIN LATERAL jsonb_array_elements(o.snapshot->'lines') x
                 WHERE p.provider='woocommerce' AND p.site_key=%s AND x->>'line_id'=p.line_id
                   AND (x->>'ecommerce_id')::bigint=%s GROUP BY p.external_order_id,p.line_id
                ) x GROUP BY external_order_id,line_id""", (site, ecommerce_id, site, ecommerce_id)).fetchall()
            parent_id = int(row[5]) if row[6] not in (None, '', '0') else 0
            products.append(dict(woo_id=int(mapping['woo_id']), parent_woo_id=parent_id, sku=mapping['sku'],
                source_key=mapping['source_key'], available=row[2],
                represented={f'{order}:{line}':qty for order, line, qty in represented}))
    if not products:
        raise ValueError('Explicit published Woo mappings required')
    return dict(revision=revision, products=products)


def publish(mp, erp, config, request=woo_request):
    outcomes = deliver_dispatches(mp, erp, config, request)
    with mp.connect() as db:
        db.execute('SELECT public.mp_commerce_release_picks()')
    stock = inventory_snapshot(mp, config['published_inventory'], config.get('site_key', 'danks.store'))
    result = request(config['woo_origin'], os.environ['WOO_MP_AUTHORIZATION'], 'POST', '/inventory', stock)
    return dict(dispatches=outcomes, inventory=result)
