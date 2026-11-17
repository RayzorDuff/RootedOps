"""Single-order production launch on the reviewed Woo/ERP/MP installation."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
from wsgiref.simple_server import make_server

from clover_sandbox import CloverSandboxEvidence
from customer_signals import request_erp_customer
from inbox import Inbox, PostgresInventory, ReviewedERP, application, deliver_one
from payment_reconciliation import reconcile_capture
from shipment_reconciliation import reconcile_shipment

SITE, ERP = 'danks.store', 'https://erp.danks.store'
STAMP = '%Y-%m-%dT%H:%M:%S'


def reviewed_order(config):
    if config.get('enabled') is not True or type(config.get('woo_order_id')) is not int or config['woo_order_id'] <= 0:
        raise ValueError('Enable a single approved numeric Woo order')
    cutoff = datetime.strptime(config['not_before_gmt'], STAMP)
    return str(config['woo_order_id']), cutoff


def admit_order(order, order_id, cutoff):
    return str(order['id']) == order_id and datetime.strptime(order['date_created_gmt'], STAMP) >= cutoff


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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('init', 'serve', 'status', 'work-once', 'capture', 'shipment'))
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--port', type=int, default=8102)
    parser.add_argument('--posting-date')
    parser.add_argument('--movement-reference')
    args = parser.parse_args()
    if os.environ.get('COMMERCE_PRODUCTION_ORDER_PILOT') != '1' or args.config.stat().st_mode & 0o077:
        parser.error('Explicit production opt-in and private config required')
    config = json.loads(args.config.read_text())
    order_id, cutoff = reviewed_order(config)
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
    if command == 'status':
        print(json.dumps(inbox.order_status(key), default=str))
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
    policy = config['draft_policy']
    if policy.get('allow_zero_tax_fixture'):
        parser.error('Use a reviewed production destination tax quote')
    mp = PostgresInventory(connector(os.environ['COMMERCE_LIVE_MP_DSN'], config['mp_database']),
                           erp_site='erp.danks.store', production=True)
    erp = ReviewedERP(ERP, os.environ['ERP_AUTHORIZATION'], {}, request_erp_customer,
                      mapping_policy=policy, production=True)
    if command == 'work-once':
        items = config['approved_item_codes']
        if not isinstance(items, list) or not items:
            parser.error('Explicit approved production Items required')
        row = dict(mappings=config['mappings'], gateways={'clover_payments': 'clover', '': 'manual_unpaid'},
                   pilot_items=frozenset(items), reviewed_mapping=True, clover_capture_pilot=True, production=True)
        print(json.dumps({'worked': deliver_one(inbox, mp, erp, site=SITE, order_id=order_id,
                                               pilot_configs={SITE: row})}))
    elif command == 'capture':
        if not args.posting_date or not config.get('clover_charge_id'):
            parser.error('Review the exact Clover charge ID and posting date')
        event, _ = inbox.completed_woo_payment_source(key)
        if event.get('processor_payment_id') != config['clover_charge_id']:
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
