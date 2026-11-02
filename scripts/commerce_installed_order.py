#!/usr/bin/env python3
"""One operator-relayed unpaid installed order; no live webhook/payment/fulfillment.

Uses the existing inbox/reservation/ERP services, with a separate empty test DB.
The psycopg2 shim is only a fixture DB-API transport for the installed image.
"""
import argparse
import base64
import json
import os
from pathlib import Path
import subprocess

from commerce_catalog_audit import native
from commerce_catalog_batch import guarded_environment
from ecwid_migrate import api, private_write
from customers import upsert_customer
from channel import upsert_draft
from inbox import ReviewedERP

MP = 'rootedops-full-test-mushroomprocess-bridge-postgres-1'
IMAGE = 'rootedops-erpnext:test2-restored-v16.13.0'
DB = 'commerce_integration_test'
SOURCE_SHA = '451393c621b64c5bd4ca7d03b1525c6253f641ae'

RUNNER = r'''
import os,sys,json,base64,hmac,secrets,psycopg2
sys.path.insert(0,'/commerce/integrations/commerce')
from inbox import Inbox,PostgresInventory
class Connection:
 def __init__(self):
  self.db=psycopg2.connect(host='127.0.0.1',dbname='commerce_integration_test',user=os.environ['PGUSER'],password=os.environ['PGPASSWORD'])
  assert self.execute('select current_database()').fetchone()[0]=='commerce_integration_test'
 def execute(self,sql,args=None):
  cursor=self.db.cursor();cursor.execute(sql,args);return cursor
 def __enter__(self):return self
 def __exit__(self,kind,value,trace):
  try:self.db.rollback() if kind else self.db.commit()
  finally:self.db.close()
a=json.load(sys.stdin);inbox=Inbox(Connection);mp=PostgresInventory(Connection,erp_site='erp-test2.danks.store')
with Connection() as db:
 assert db.execute('select marker from rootedops_commerce_fixture').fetchone()[0]=='installed-order-v1'
action=a['action'];out={}
if action=='seed':
 with Connection() as db:
  assert not db.execute('select exists(select 1 from products) or exists(select 1 from items)').fetchone()[0], 'Fixture already seeded; use stored receipt'
  item=db.execute("insert into items(item_id,name,category,active) values('TEST2-TAX-MERCH','Synthetic installed order','grain',true) returning nocopk").fetchone()[0]
  loc=db.execute("insert into locations(name,active,type) values('Commerce isolated fixture',true,'Storage') returning nocopk").fetchone()[0]
  db.execute('insert into products(item_id,storage_location_id,use_by) values(%s,%s,current_date+7),(%s,%s,current_date+7)',(item,loc,item,loc))
  ec=db.execute("insert into ecommerce(name,item_id,provider,site_key,external_product_id,external_sku,erp_item_code,sync_enabled,status) values('Commerce installed fixture',%s,'woocommerce','shop-test2.danks.store',%s,'TEST2-TAX-MERCH','TEST2-TAX-MERCH',true,'Sterilized') returning nocopk",(item,str(a['woo_product']))).fetchone()[0]
  out={'ecommerce_id':ec,'item':item}
elif action=='receive':
 raw=json.dumps(a['order'],separators=(',',':')).encode();secret=secrets.token_urlsafe(40)
 sig=base64.b64encode(hmac.digest(secret.encode(),raw,'sha256')).decode()
 kw=dict(secrets=[secret],site='shop-test2.danks.store',mappings=a['mappings'],gateways={'clover_payments':'clover'})
 try:inbox.receive(raw,base64.b64encode(b'bad signature').decode(),**kw)
 except ValueError:pass
 else:raise AssertionError('Invalid signature accepted')
 first=inbox.receive(raw,sig,**kw);assert inbox.receive(raw,sig,**kw)['duplicate']
 claim=inbox.claim();assert claim is not None
 receipt=mp(claim['payload']);inbox.record(claim,'mp',receipt)
 out={'claim':dict(claim,key=list(claim['key'])),'mp':receipt,'duplicate':True,'invalid_signature_rejected':True}
elif action=='finish':
 claim=a['claim'];receipt=a['erp'];inbox.record(claim,'erp',receipt);mp.link_erp(claim['payload'],receipt);inbox.finish(claim)
 assert inbox.claim() is None
 with Connection() as db:
  out={'orders':db.execute('select count(*) from mp_commerce_orders').fetchone()[0],
   'reserved':db.execute('select coalesce(sum(quantity),0) from mp_commerce_reservations').fetchone()[0],
   'erp_links':db.execute('select count(*) from mp_commerce_erp_links').fetchone()[0],
   'events':db.execute('select count(*) from mp_commerce_events').fetchone()[0],'delivery':inbox.status()}
elif action=='eligibility':
 try:
  with Connection() as db:db.execute("select mp_commerce_confirm_reservation('woocommerce','shop-test2.danks.store',%s)",(str(a['order']),))
 except Exception:out={'unpaid_fulfillment_rejected':True}
 else:raise AssertionError('Unpaid order became fulfillment eligible')
else:raise ValueError('Unknown fixture action')
print(json.dumps(out))
'''

ERP = r'''
import json,sys,frappe
from rootedops_commerce.order_service import stage_order
a=json.load(sys.stdin);frappe.init(site='erp-test2.danks.store');frappe.connect();frappe.set_user('Administrator')
try:
 assert frappe.conf.maintenance_mode and frappe.conf.pause_scheduler
 # Request-local opt-in only. No site-wide integration or scheduler activation.
 frappe.conf.commerce_order_integration_enabled=1
 result=stage_order(json.dumps(a));again=stage_order(json.dumps(a));assert again==result
 order=frappe.get_doc('Sales Order',result['sales_order'])
 assert order.docstatus==0 and order.customer==a['reviewed_draft']['customer']
 assert not result.get('sales_invoice') and not result.get('payment_entry')
 frappe.db.commit();print(json.dumps(result))
except Exception:frappe.db.rollback();raise
finally:frappe.destroy()
'''


def credentials():
    data = json.loads(subprocess.check_output(['docker', 'inspect', MP]))[0]
    return dict(x.split('=', 1) for x in data['Config']['Env'] if '=' in x)


def runner(value):
    env = credentials(); process_env = dict(os.environ, PGUSER=env['POSTGRES_USER'], PGPASSWORD=env['POSTGRES_PASSWORD'])
    root = str(Path(__file__).resolve().parents[1])
    command = ['docker', 'run', '--rm', '-i', '--user', '0', '--network', 'container:' + MP,
               '-e', 'PGUSER', '-e', 'PGPASSWORD', '-v', root + ':/commerce:ro',
               '--entrypoint', '/home/frappe/frappe-bench/env/bin/python', IMAGE, '-c', RUNNER]
    p = subprocess.run(command, input=json.dumps(value), text=True, capture_output=True, env=process_env, timeout=30)
    if p.returncode:
        raise RuntimeError(p.stderr[-1600:])
    return json.loads(p.stdout)


def prepare(source):
    assert subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()==SOURCE_SHA
    command = ['docker','exec','-i',MP,'sh','-c','psql -X -U "$POSTGRES_USER" -d commerce_integration_test -v ON_ERROR_STOP=1 -q']
    # Creation refuses an existing database; there is intentionally no reset path.
    subprocess.run(['docker','exec',MP,'sh','-c','createdb -U "$POSTGRES_USER" commerce_integration_test'],check=True)
    for path in sorted((source/'schema/pgsql').glob('0*.sql')):
        p=subprocess.run(command,input=path.read_text(),capture_output=True,text=True)
        if p.returncode:raise RuntimeError('Isolated schema migration failed: '+path.name+' '+p.stderr[-800:])
    sql=Path(__file__).resolve().parents[1]/'integrations/commerce/inbox.sql'
    subprocess.run(command,input=sql.read_text()+"\ncreate table rootedops_commerce_fixture(marker text primary key);insert into rootedops_commerce_fixture values('installed-order-v1');",text=True,check=True,capture_output=True)
    print(json.dumps({'database':DB,'schema_commit':SOURCE_SHA,'restored_database_modified':False}))


def exercise(environment):
    target,private=guarded_environment(environment)
    work=private/'installed-order';work.mkdir(mode=0o700,exist_ok=True)
    state_path=work/'state.json'
    if state_path.exists():
        raise ValueError('Existing exercise receipt: inspect/reconcile it; never create another order automatically')
    c=json.loads((private/'wordpress-credentials.json').read_text())
    auth='Basic '+base64.b64encode((c['username']+':'+c['application_password']).encode()).decode()
    customer=upsert_customer(target['shop'],auth,'synthetic:installed-order-v1',
        {'email':'commerce-acceptance@example.invalid','first_name':'Commerce','last_name':'Acceptance'},mail_sink_verified=True)
    key='synthetic:installed-order-product-v1'
    product=upsert_draft(target['shop'],auth,{'source_key':key,'item':{},'expected_currency':'USD',
        'woocommerce':{'name':'Synthetic installed commerce acceptance','sku':'TEST2-TAX-MERCH','status':'draft',
         'catalog_visibility':'hidden','regular_price':'12.00','manage_stock':True,'stock_quantity':0,
         'meta_data':[{'key':'_rootedops_source_key','value':key}]}})
    seed=runner({'action':'seed','woo_product':product['id']})
    order=api(target['shop']+'/wp-json/wc/v3/orders',auth,'POST',{'status':'pending','currency':'USD',
        'customer_id':customer['external_customer_id'],'payment_method':'clover_payments','set_paid':False,
        'billing':{'first_name':'Commerce','last_name':'Acceptance','email':'commerce-acceptance@example.invalid'},
        'line_items':[{'product_id':product['id'],'quantity':1,'subtotal':'12.00','total':'12.00'}],
        'meta_data':[{'key':'_rootedops_source_key','value':'synthetic:installed-order-v1'}]})
    state={'woo_order':order['id'],'woo_customer':customer['external_customer_id'],'woo_product':product['id'],'seed':seed}
    private_write(state_path,state)
    order=api(target['shop']+'/wp-json/wc/v3/orders/'+str(order['id']),auth)
    assert order['customer_id']==customer['external_customer_id'] and order['total']=='12.00' and not order['date_paid'] and order['total_tax']=='0.00'
    mappings={str(product['id']):{'sku':'TEST2-TAX-MERCH','ecommerce_id':seed['ecommerce_id'],'erp_item_code':'TEST2-TAX-MERCH'}}
    received=runner({'action':'receive','order':order,'mappings':mappings});private_write(work/'received.json',received)
    customer_name=native("import frappe,json;frappe.init(site='erp-test2.danks.store');frappe.connect();print(json.dumps(frappe.db.get_value('Customer',{'customer_name':'RootedOps Tax Acceptance Fixture'},'name')));frappe.destroy()",{})
    draft={'customer':customer_name,'company':'Dank Mushrooms, LLC','currency':'USD',
        'conversion_rate':1,'transaction_date':order['date_created'][:10],'delivery_date':order['date_created'][:10],
        'docstatus':0,'ignore_pricing_rule':1,'items':[{'item_code':'TEST2-TAX-MERCH','qty':1,'rate':12}],
        'taxes':[],'remarks':'Synthetic installed order. Unpaid; no fulfillment. Woo customer '+str(customer['external_customer_id'])}
    event=received['claim']['payload'];approved={'|'.join([event['provider'],event['site_key'],event['external_order_id']]):draft}
    erp=ReviewedERP(target['erp'],'operator-native-transport',approved,
        lambda url,authorization,method,payload:{'message':native(ERP,json.loads(payload['payload']))})
    result=erp(event,received['mp']);private_write(work/'erp.json',result)
    finished=runner({'action':'finish','claim':received['claim'],'erp':result})
    eligibility=runner({'action':'eligibility','order':order['id']})
    report=dict(state,erp=result,mp=finished,**eligibility,duplicate_webhook=True,invalid_signature_rejected=True,
        tax_total='0.00',destination_tax_validated=False,automatic_webhook_route=False,clover_capture_tested=False,
        physical_fulfillment_tested=False,transport='operator-relayed actual Woo REST snapshot; native ERP callback')
    private_write(work/'result.json',report);print(json.dumps(report))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('environment',type=Path)
    p.add_argument('--prepare-schema',type=Path);a=p.parse_args()
    guarded_environment(a.environment)
    prepare(a.prepare_schema) if a.prepare_schema else exercise(a.environment)
