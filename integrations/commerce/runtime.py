#!/usr/bin/env python3
"""Opt-in loopback staging inbox/worker CLI. Never resets a database."""
import argparse
import json
import os
from pathlib import Path
import sys
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


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['init','serve','work-once','status','replay','reconcile-order'])
    p.add_argument('--config',type=Path);p.add_argument('--event-key',nargs=3)
    p.add_argument('--order-key',nargs=3)
    a=p.parse_args();connect=connect_test(os.environ['COMMERCE_INBOX_DSN']);inbox=Inbox(connect)
    if a.command=='init':
        with connect() as db:db.execute(Path(__file__).with_name('inbox.sql').read_text())
    elif a.command=='status':print(json.dumps(inbox.status()))
    elif a.command=='replay':
        if not a.event_key:p.error('replay requires --event-key PROVIDER SITE EVENT_ID')
        inbox.replay(tuple(a.event_key))
    elif a.command=='serve':
        if not a.config:p.error('--config required')
        config=json.loads(a.config.read_text())
        sites={}
        for site,row in config['sites'].items():
            sites[site]={'secrets':[os.environ[name] for name in row['secret_envs']],
                         'mappings':row['mappings'],'gateways':row['gateways']}
        # No public bind switch. Use only an independently reviewed test proxy.
        with make_server('127.0.0.1',8100,application(inbox,sites)) as server:server.serve_forever()
    else:
        if not a.config:p.error('--config required')
        approved=json.loads(a.config.read_text())['approved_erp_drafts']
        erp=ReviewedERP('https://erp-test.danks.store',os.environ['ERP_AUTHORIZATION'],approved,api)
        mp=PostgresInventory(connect_test(os.environ['MP_TEST_DSN']))
        if a.command=='reconcile-order':
            if not a.order_key:p.error('reconcile-order requires --order-key PROVIDER SITE ORDER_ID')
            print(json.dumps(reconcile_order(inbox,mp,erp,tuple(a.order_key))))
        else:print(json.dumps({'worked':deliver_one(inbox,mp,erp)}))

if __name__=='__main__':main()
