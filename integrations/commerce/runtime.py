#!/usr/bin/env python3
"""Opt-in loopback staging inbox/worker CLI. Never resets a database."""
import argparse
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
from wsgiref.simple_server import make_server
from inbox import Inbox, PostgresInventory, ReviewedERP, application, deliver_one, reconcile_order
from ecwid_migrate import api


def connect_test(dsn):
    import psycopg
    from psycopg.conninfo import conninfo_to_dict
    info=conninfo_to_dict(dsn)
    if os.environ.get('COMMERCE_STAGING_ONLY')!='1':raise ValueError('Explicit staging opt-in required')
    if info.get('dbname') not in ('commerce_test','commerce_integration_test','mushroomprocess_test'):
        raise ValueError('Refusing non-test database')
    if info.get('host') not in ('localhost','127.0.0.1','commerce-postgres') or info.get('hostaddr'):
        raise ValueError('Only explicit local disposable database endpoints accepted')
    def connect():
        db=psycopg.connect(dsn)
        if db.execute('SELECT current_database()').fetchone()[0]!=info['dbname']:
            db.close();raise ValueError('Actual database identity mismatch')
        return db
    return connect


def order_site(site):
    from staging_origin import staging_origin
    if staging_origin('https://' + site, 'shop') != 'https://' + site:
        raise ValueError('Use the exact staging host as order site key')
    return site


def pilot_config(row):
    items = row['synthetic_item_codes']
    if not isinstance(items, list) or not items or any(
            not isinstance(item, str) or not item.strip() for item in items):
        raise ValueError('Explicit synthetic pilot Item codes required')
    return {'mappings': row['mappings'], 'gateways': row['gateways'], 'pilot_items': frozenset(items),
            'reviewed_mapping': row.get('draft_policy') is not None,
            'clover_capture_pilot': row.get('clover_capture_pilot') is True}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['init','serve','work-once','status','replay','reconcile-order','reconcile-capture','work-customers-once','order-status'])
    p.add_argument('--config',type=Path);p.add_argument('--event-key',nargs=3)
    p.add_argument('--order-key',nargs=3)
    p.add_argument('--customer-site')
    p.add_argument('--order-site')
    p.add_argument('--posting-date')
    p.add_argument('--port', type=int, default=8100, help='loopback receiver port')
    a=p.parse_args();connect=connect_test(os.environ['COMMERCE_INBOX_DSN']);inbox=Inbox(connect)
    if a.command=='init':
        with connect() as db:db.execute(Path(__file__).with_name('inbox.sql').read_text())
    elif a.command=='status':print(json.dumps(inbox.status()))
    elif a.command == 'order-status':
        if not a.order_key or a.order_key[0] != 'woocommerce':
            p.error('--order-key woocommerce STAGING_SITE WOO_ORDER_ID required')
        order_site(a.order_key[1])
        print(json.dumps(inbox.order_status(tuple(a.order_key)), default=str))
    elif a.command=='replay':
        if not a.event_key:p.error('replay requires --event-key PROVIDER SITE EVENT_ID')
        inbox.replay(tuple(a.event_key))
    elif a.command=='serve':
        if not a.config:p.error('--config required')
        config=json.loads(a.config.read_text())
        sites={}
        from tax_policy import load_policy
        for site,row in config.get('sites', {}).items():
            order_site(site)
            if row.get('unpaid_pilot') is True:
                pilot_config(row)
                sites[site] = {'secrets': [os.environ[name] for name in row['secret_envs']],
                               'unpaid_pilot': True}
                continue
            # Every other staging site must point to an approved, private,
            # read-only classification file. Missing policy fails closed at
            # server startup, before any webhook can be acknowledged.
            if not row.get('tax_classification_file'):
                raise ValueError('Approved tax classification file required for webhook site')
            policy=load_policy(row['tax_classification_file'])
            sites[site]={'secrets':[os.environ[name] for name in row['secret_envs']],
                         'mappings':row['mappings'],'gateways':row['gateways'],
                         'tax_policy':policy}
        from staging_origin import staging_origin
        customer_sites = {}
        for site, row in config.get('customer_sites', {}).items():
            if staging_origin('https://' + site, 'shop') != 'https://' + site:
                raise ValueError('Use exact staging host as customer site key')
            customer_sites[site] = {'secrets': [os.environ[name] for name in row['secret_envs']]}
        # No public bind switch. Use only an independently reviewed test proxy.
        with make_server('127.0.0.1', a.port, application(inbox, sites, customer_sites)) as server:
            server.serve_forever()
    elif a.command=='work-customers-once':
        from customer_signals import deliver_customer, request_erp_customer
        from staging_origin import customer_pair
        if not a.config or not a.customer_site:
            p.error('--config and --customer-site required')
        config = json.loads(a.config.read_text())
        row = config['customer_sites'][a.customer_site]
        erp, shop = customer_pair(row['erp_base_url'], 'https://' + a.customer_site,
                                  production_erp_pilot=row.get('production_erp_pilot', False))
        print(json.dumps({'worked': deliver_customer(
            inbox, erp, os.environ['ERP_AUTHORIZATION'], request_erp_customer, site=urlsplit(shop).hostname)}))
    else:
        if not a.config:p.error('--config required')
        from staging_origin import staging_pair
        from tax_policy import load_policy

        config = json.loads(a.config.read_text())
        base = config.get('erp_base_url', 'https://erp-test.danks.store')
        site = a.order_site
        if a.command in ('reconcile-order', 'reconcile-capture'):
            if not a.order_key or a.order_key[0] != 'woocommerce':
                p.error('--order-key woocommerce STAGING_SITE WOO_ORDER_ID required')
            site = a.order_key[1]
        if site is None:
            site = urlsplit(base).hostname.replace('erp-', 'shop-', 1)
        staging_pair(base, 'https://' + order_site(site))
        row = config['sites'][site]
        tax_policies, pilot_configs = {}, {}
        if row.get('unpaid_pilot') is True:
            pilot_configs[site] = pilot_config(row)
        else:
            tax_policies[site] = load_policy(row['tax_classification_file'])
        erp = ReviewedERP(base, os.environ['ERP_AUTHORIZATION'], config.get('approved_erp_drafts', {}),
                          api, mapping_policy=row.get('draft_policy'))
        mp = PostgresInventory(connect_test(os.environ['MP_TEST_DSN']), erp_site=urlsplit(erp.base).hostname)
        if a.command == 'reconcile-order':
            print(json.dumps(reconcile_order(inbox, mp, erp, tuple(a.order_key))))
        elif a.command == 'reconcile-capture':
            from clover_sandbox import CloverSandboxEvidence
            from payment_reconciliation import reconcile_capture
            if not a.posting_date or row.get('clover_capture_pilot') is not True:
                p.error('Explicit sandbox capture pilot and --posting-date required')
            clover = CloverSandboxEvidence(site_key=site, enabled=True,
                merchant_id=os.environ['CLOVER_SANDBOX_MERCHANT_ID'],
                private_key=os.environ['CLOVER_SANDBOX_PRIVATE_KEY'])
            print(json.dumps(reconcile_capture(inbox, mp, erp, clover, tuple(a.order_key),
                  a.posting_date, os.environ['COMMERCE_CAPTURE_EVIDENCE_KEY'])))
        else:
            print(json.dumps({'worked': deliver_one(inbox, mp, erp, site=site,
                              tax_policies=tax_policies, pilot_configs=pilot_configs)}))


if __name__ == '__main__':
    main()
