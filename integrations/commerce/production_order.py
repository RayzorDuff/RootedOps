"""Production Woo order operation on the reviewed Woo/ERP/MP installation."""
import argparse
from datetime import datetime
import json
import os
import re
from pathlib import Path
from wsgiref.simple_server import make_server

from clover_sandbox import CloverSandboxEvidence
from customer_signals import request_erp_customer
from inbox import Inbox, PostgresInventory, ReviewedERP, application, deliver_one
from payment_reconciliation import reconcile_capture
from orders import normalize_order
from shipment_reconciliation import reconcile_shipment
from mp_publication import publish

SITE, ERP = 'danks.store', 'https://erp.danks.store'
STAMP = '%Y-%m-%dT%H:%M:%S'


def reviewed_order(config):
    if config.get('enabled') is not True or type(config.get('woo_order_id')) is not int or config['woo_order_id'] <= 0:
        raise ValueError('Enable a single approved numeric Woo order')
    cutoff = datetime.strptime(config['not_before_gmt'], STAMP)
    return str(config['woo_order_id']), cutoff


def admit_order(order, order_id, cutoff):
    return ((order_id is None or str(order['id']) == order_id)
            and order.get('status') not in ('checkout-draft', 'auto-draft')
            and datetime.strptime(order['date_created_gmt'], STAMP) >= cutoff)


def order_scope(config, command, selected=None):
    if config.get('mode', 'pilot') == 'pilot':
        order_id, cutoff = reviewed_order(config)
        if selected is not None and selected != order_id:
            raise ValueError('Cannot select another order in pilot mode')
        return order_id, cutoff
    if config.get('mode') != 'review' or config.get('enabled') is not True:
        raise ValueError('Explicit production review mode required')
    cutoff = datetime.strptime(config['not_before_gmt'], STAMP)
    if command in ('serve', 'init', 'queue', 'publish', 'cycle'):
        if selected is not None:
            raise ValueError('This command does not take an order ID')
        return None, cutoff
    if not selected or not re.fullmatch(r'[1-9][0-9]{0,18}', selected) or int(selected) >= 2**63:
        raise ValueError('Select a single numeric Woo order with --order-id')
    return selected, cutoff


def pilot_config(config):
    items = config['approved_item_codes']
    if not isinstance(items, list) or not items:
        raise ValueError('Explicit approved production Items required')
    return dict(mappings=config['mappings'], gateways={'clover_payments': 'clover', '': 'manual_unpaid'},
                pilot_items=frozenset(items), reviewed_mapping=True, clover_capture_pilot=True, production=True)


def review_order(inbox, key, config, cutoff):
    raw, identity = inbox.latest_order_source(key)
    if not admit_order(raw, key[2], cutoff):
        raise ValueError('Receipt predates the approved cutoff')
    event = normalize_order(raw, identity, **pilot_config(config))
    commercial = event['commercial']
    lines = [dict(line_id=row['line_id'], item_code=row['erp_item_code'], quantity=row['quantity'],
                  line_total=commercial['line_totals'][row['line_id']]) for row in event['lines']]
    return dict(order_id=key[2], event_id=event['event_id'], status=event['status'], currency=event['currency'],
                total=event['total'], shipping=commercial['shipping'], tax=commercial['tax'],
                destination_hash=commercial['destination'], lines=lines,
                has_clover_reference=bool(event['processor_payment_id']), refunds=event['refunds'])


def order_ledger(mp, key):
    with mp.connect() as db:
        row = db.execute("""SELECT o.status, o.reservation_confirmed, o.inventory_committed,
                     l.sales_order, l.sales_invoice, l.payment_entry,
                     (SELECT coalesce(sum(r.quantity),0) FROM public.mp_commerce_reservations r
                       WHERE (r.provider,r.site_key,r.external_order_id) =
                             (o.provider,o.site_key,o.external_order_id)),
                     (SELECT count(*) FROM public.mp_commerce_shipped_units p
                       WHERE (p.provider,p.site_key,p.external_order_id) =
                             (o.provider,o.site_key,o.external_order_id))
                FROM public.mp_commerce_orders o LEFT JOIN public.mp_commerce_erp_links l
                 USING (provider,site_key,external_order_id)
                WHERE (o.provider,o.site_key,o.external_order_id)=(%s,%s,%s)""", key).fetchone()
    columns = ('mp_status', 'reservation_confirmed', 'inventory_committed', 'sales_order',
               'sales_invoice', 'payment_entry', 'held_units', 'shipped_units')
    return dict(zip(columns, row)) if row else {'mp_status': 'missing'}


def connector(dsn, expected_name):
    import psycopg
    from psycopg.conninfo import conninfo_to_dict
    if not expected_name or conninfo_to_dict(dsn).get('dbname') != expected_name:
        raise ValueError('Explicit reviewed Postgres database identity required')

    def connect():
        db = psycopg.connect(dsn)
        if db.execute('SELECT current_database()').fetchone()[0] != expected_name:
            db.close()
            raise ValueError('Postgres database identity drift')
        return db
    return connect


def cycle(inbox, mp, config):
    """Keep later receipts moving after an order's private quote/ERP review."""
    if config.get('mode') != 'review' or config.get('automation_enabled') is not True:
        raise ValueError('Enable the reviewed multi-order cycle explicitly')
    directory = Path(config['quote_directory'])
    if not directory.is_dir() or directory.stat().st_mode & 0o077:
        raise ValueError('Private reviewed quote directory required')
    base_policy = config['draft_policy']
    if base_policy.get('allow_zero_tax_fixture'):
        raise ValueError('Production requires reviewed tax quotes')
    clover = None
    if config.get('automatic_capture') is True:
        clover = CloverSandboxEvidence(site_key=SITE, merchant_id=os.environ['CLOVER_LIVE_MERCHANT_ID'],
                  private_key=os.environ['CLOVER_LIVE_PRIVATE_KEY'], enabled=True, production=True)
    outcomes = []
    for path in sorted(directory.glob('*.json')):
        order_id = path.stem
        order_scope(config, 'work-once', order_id)
        if path.stat().st_mode & 0o077:
            raise ValueError('Private reviewed quote required')
        quote = json.loads(path.read_text())
        if quote.get('source_order') != order_id:
            raise ValueError('Reviewed quote differs from its numeric filename')
        policy = dict(base_policy, tax_quotes={**base_policy.get('tax_quotes', {}), order_id: quote})
        erp = ReviewedERP(ERP, os.environ['ERP_AUTHORIZATION'], {}, request_erp_customer,
                          mapping_policy=policy, production=True)
        worked = deliver_one(inbox, mp, erp, site=SITE, order_id=order_id,
                             pilot_configs={SITE: pilot_config(config)})
        outcome = dict(order_id=order_id, worked=worked)
        if clover is not None:
            try:
                key = ('woocommerce', SITE, order_id)
                event, _ = inbox.completed_woo_payment_source(key)
                if event.get('refunds'):
                    outcome['capture'] = 'refund_review'
                elif event['status'] in ('processing', 'completed') and not order_ledger(mp, key).get('reservation_confirmed'):
                    posting_date = config.get('capture_posting_dates', {}).get(order_id)
                    if posting_date is None:
                        outcome['capture'] = 'posting_date_review'
                    else:
                        outcome['capture'] = reconcile_capture(inbox, mp, erp, clover, key,
                            posting_date, os.environ['COMMERCE_CAPTURE_EVIDENCE_KEY'],
                            production=True)['status']
            except Exception:
                outcome['capture'] = 'capture_review'
        outcomes.append(outcome)
    return outcomes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('init', 'serve', 'status', 'queue', 'review', 'ledger', 'work-once', 'capture', 'shipment', 'replay', 'publish', 'cycle'))
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--port', type=int, default=8102)
    parser.add_argument('--order-id')
    parser.add_argument('--charge-id')
    parser.add_argument('--tax-quote', type=Path)
    parser.add_argument('--posting-date')
    parser.add_argument('--event-id')
    parser.add_argument('--movement-reference')
    args = parser.parse_args()
    if os.environ.get('COMMERCE_PRODUCTION_ORDER_PILOT') != '1' or args.config.stat().st_mode & 0o077:
        parser.error('Explicit production opt-in and private config required')
    config = json.loads(args.config.read_text())
    order_id, cutoff = order_scope(config, args.command, args.order_id)
    key = ('woocommerce', SITE, order_id)
    if config['inbox_database'] == config['mp_database']:
        parser.error('Use a dedicated order inbox database')
    connect_inbox = connector(os.environ['COMMERCE_LIVE_INBOX_DSN'], config['inbox_database'])
    inbox = Inbox(connect_inbox)
    command = args.command
    if command == 'init':
        with connect_inbox() as db:
            db.execute(Path(__file__).with_name('inbox.sql').read_text())
        return
    if command == 'queue':
        print(json.dumps(inbox.order_queue(*key[:2]), default=str))
        return
    if command == 'review':
        print(json.dumps(review_order(inbox, key, config, cutoff)))
        return
    if command == 'status':
        print(json.dumps(inbox.order_status(key), default=str))
        return
    if command == 'replay':
        if not args.event_id or not any(row['event_id'] == args.event_id
                                       for row in inbox.order_status(key)):
            parser.error('Receipt is outside the approved production order')
        inbox.replay((key[0], key[1], args.event_id))
        return
    if command == 'serve':
        secret = os.environ['COMMERCE_LIVE_WEBHOOK_SECRET']
        if len(secret) < 32:
            parser.error('Dedicated production webhook secret required')
        route = dict(unpaid_pilot=True, secrets=[secret],
                     admit=lambda order: admit_order(order, order_id, cutoff))
        with make_server('127.0.0.1', args.port, application(inbox, {SITE: route})) as server:
            server.serve_forever()
        return
    mp = PostgresInventory(connector(os.environ['COMMERCE_LIVE_MP_DSN'], config['mp_database']),
                           erp_site='erp.danks.store', production=True)
    if command == 'ledger':
        print(json.dumps(order_ledger(mp, key), default=str))
        return
    if command == 'cycle':
        result = {'orders': cycle(inbox, mp, config)}
        if config.get('publication_enabled') is True:
            erp = ReviewedERP(ERP, os.environ['ERP_AUTHORIZATION'], {}, request_erp_customer, production=True)
            result['publication'] = publish(mp, erp, config)
        print(json.dumps(result))
        return
    if command == 'publish':
        if config.get('publication_enabled') is not True:
            parser.error('Explicit MP publication opt-in required')
        erp = ReviewedERP(ERP, os.environ['ERP_AUTHORIZATION'], {}, request_erp_customer, production=True)
        print(json.dumps(publish(mp, erp, config)))
        return
    policy = config['draft_policy']
    if args.tax_quote is not None:
        if command != 'work-once' or args.tax_quote.stat().st_mode & 0o077:
            parser.error('Use a private quote file only for work-once')
        quote = json.loads(args.tax_quote.read_text())
        if not isinstance(quote, dict) or quote.get('source_order') != order_id:
            parser.error('Quote does not belong to the selected Woo order')
        policy = dict(policy, tax_quotes={**policy.get('tax_quotes', {}), order_id: quote})
    if policy.get('allow_zero_tax_fixture'):
        parser.error('Use a reviewed production destination tax quote')
    erp = ReviewedERP(ERP, os.environ['ERP_AUTHORIZATION'], {}, request_erp_customer,
                      mapping_policy=policy, production=True)
    if command == 'work-once':
        row = pilot_config(config)
        print(json.dumps({'worked': deliver_one(inbox, mp, erp, site=SITE, order_id=order_id,
                                               pilot_configs={SITE: row})}))
    elif command == 'capture':
        charge = args.charge_id if config.get('mode') == 'review' else config.get('clover_charge_id')
        if not args.posting_date or not charge:
            parser.error('Review the exact Clover charge ID and posting date')
        event, _ = inbox.completed_woo_payment_source(key)
        if event.get('processor_payment_id') != charge:
            parser.error('Woo receipt differs from the approved Clover charge')
        clover = CloverSandboxEvidence(site_key=SITE, merchant_id=os.environ['CLOVER_LIVE_MERCHANT_ID'],
                    private_key=os.environ['CLOVER_LIVE_PRIVATE_KEY'], enabled=True, production=True)
        print(json.dumps(reconcile_capture(inbox, mp, erp, clover, key, args.posting_date,
                         os.environ['COMMERCE_CAPTURE_EVIDENCE_KEY'], production=True)))
    else:
        if not args.movement_reference:
            parser.error('--movement-reference required')
        print(json.dumps(reconcile_shipment(mp, erp, key, args.movement_reference,
                         os.environ['COMMERCE_SHIPMENT_EVIDENCE_KEY'], production=True)))


if __name__ == '__main__':
    main()
