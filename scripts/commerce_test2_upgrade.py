#!/usr/bin/env python3
"""Reversible installed commerce 0.3.0→0.3.1 update on Test2 only; no schema rebuild."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
from datetime import datetime,timezone
from commerce_staging_targets import targets
CONTAINER='rootedops-full-test-erpnext-backend-1'
BENCH='/home/frappe/frappe-bench'
APP=BENCH+'/apps/rootedops_commerce'
OLD_API='830229e8d20335007e72369732681dee172cf6e185479fcf3eccb46b9b84340d'
NEW_API='c6b348c56641aeba47d17cd1866a1ae65f204c6bcf3b91a3bbb70eb5f78ea91b'
FILES=('rootedops_commerce/api.py','rootedops_commerce/__init__.py','rootedops_commerce/tests/test_catalog.py')
PROBE='''import sys,json,hashlib,pathlib,importlib.metadata,importlib.util,frappe,rootedops_commerce
import rootedops_commerce.api as api
frappe.init(site=sys.argv[1]);frappe.connect()
records={}
for table in ['Item','Item Price','Commercial Product Content','Commerce Channel Mapping','Customer','Sales Order','Sales Order Item','Sales Invoice','Sales Invoice Item','Payment Entry','Payment Entry Reference','Contact','Address']:
 rows=frappe.db.sql('SELECT * FROM `tab'+table+'` ORDER BY name',as_dict=True)
 records[table]={'count':len(rows),'sha256':hashlib.sha256(json.dumps(rows,sort_keys=True,default=str).encode()).hexdigest()}
r={'module_version':rootedops_commerce.__version__,'package_version':importlib.metadata.version('rootedops_commerce'),'api_sha256':hashlib.sha256(pathlib.Path(api.__file__).read_bytes()).hexdigest(),'flit_available':importlib.util.find_spec('flit_core') is not None,'maintenance_mode':frappe.conf.get('maintenance_mode'),'pause_scheduler':frappe.conf.get('pause_scheduler'),'outgoing':frappe.db.count('Email Account',{'enable_outgoing':1}),'webhooks':frappe.db.count('Webhook',{'enabled':1}),'notifications':frappe.db.count('Notification',{'enabled':1}),'records':records}
frappe.db.rollback();frappe.destroy();print(json.dumps(r))
'''


def validate_before(state):
    if not state['maintenance_mode'] or not state['pause_scheduler'] or any(state[k] for k in ('outgoing','webhooks','notifications')):
        raise ValueError('Paused isolated ERP required')
    allowed={('0.3.0','0.3.0',OLD_API),('0.3.1','0.3.1',NEW_API),('0.3.1','0.3.0',NEW_API)}
    if (state['module_version'],state['package_version'],state['api_sha256']) not in allowed:
        raise ValueError('Unexpected installed source/version; do not overwrite')
    if not state['flit_available']:raise ValueError('Offline flit_core build backend required before app update')


def validate_after(before,after):
    validate_before(after)
    if after['api_sha256']!=NEW_API or after['module_version']!='0.3.1' or after['package_version']!='0.3.1':
        raise ValueError('Source and installed package metadata must both be 0.3.1')
    if before['records']!=after['records']:raise ValueError('Protected ERP record fingerprint changed; investigate without restoring database')


def run(environment,apply=False):
    if os.geteuid()!=0:raise ValueError('Run in the authorized Test2 sudo terminal')
    p=environment.resolve();site=targets(p)['erp'].split('://',1)[1]
    if site!='erp-test2.danks.store':raise ValueError('Only Test2 ERP accepted')
    root=Path(__file__).resolve().parents[1];source=root/'erpnext/apps/rootedops_commerce'
    if hashlib.sha256((source/'rootedops_commerce/api.py').read_bytes()).hexdigest()!=NEW_API:raise ValueError('Reviewed 0.3.1 source required')
    c=json.loads(subprocess.check_output(['docker','inspect',CONTAINER]))[0];labels=c['Config']['Labels'];nets=c['NetworkSettings']['Networks']
    if labels.get('com.docker.compose.project')!='rootedops-full-test' or labels.get('com.docker.compose.service')!='erpnext-backend' or not c['State']['Running']:raise ValueError('Wrong test ERP container')
    if list(nets)!=['rootedops-full-test_default'] or any(x is not None for x in (c['NetworkSettings']['Ports'] or {}).values()):raise ValueError('Unpublished internal ERP required')
    network=json.loads(subprocess.check_output(['docker','network','inspect','rootedops-full-test_default']))[0]
    if not network['Internal'] or network['Id']!=nets['rootedops-full-test_default']['NetworkID']:raise ValueError('Network drift')
    def probe():
        r=subprocess.run(['docker','exec','-w',BENCH+'/sites',CONTAINER,BENCH+'/env/bin/python','-c',PROBE,site],capture_output=True,text=True,check=True)
        return json.loads(r.stdout)
    before=probe();validate_before(before)
    if not apply:print('Installed-app preflight passed; --apply required.');return
    evidence=p/'private'/('commerce-upgrade-031-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));evidence.mkdir(mode=0o700)
    def save(name,data):
        f=evidence/name;f.write_text(json.dumps(data,indent=2));f.chmod(0o600)
    save('before.json',before);backup=evidence/'app-before.tar'
    with backup.open('xb') as f:
        backup.chmod(0o600)
        subprocess.run(['docker','exec',CONTAINER,'tar','--exclude=__pycache__','--exclude=.git','-cf','-','-C',BENCH+'/apps','rootedops_commerce'],stdout=f,check=True)
    def install():
        with (evidence/'pip.log').open('a') as log:
            subprocess.run(['docker','exec','-w',BENCH,CONTAINER,BENCH+'/env/bin/pip','install','--no-deps','--no-build-isolation','--no-index','-e','apps/rootedops_commerce'],stdout=log,stderr=log,check=True)
        (evidence/'pip.log').chmod(0o600)
    try:
        for name in FILES:
            subprocess.run(['docker','cp',str(source/name),CONTAINER+':'+APP+'/'+name],check=True)
            subprocess.run(['docker','exec','-u','0',CONTAINER,'chown','frappe:frappe',APP+'/'+name],check=True)
        install();after=probe();validate_after(before,after)
        subprocess.run(['docker','exec','-w',BENCH,CONTAINER,'bench','--site',site,'clear-cache'],check=True)
        subprocess.run(['docker','restart',CONTAINER],check=True,stdout=subprocess.DEVNULL)
        final=probe();validate_after(before,final);save('after.json',final)
        save('receipt.json',{'source_sha':subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip(),'image':c['Image'],'version':'0.3.1','api_sha256':NEW_API,'protected_records_unchanged':True,'schema_migration':False,'backup_sha256':hashlib.sha256(backup.read_bytes()).hexdigest()})
    except Exception:
        try:
            with backup.open('rb') as f:subprocess.run(['docker','exec','-i','-u','0',CONTAINER,'tar','-xf','-','-C',BENCH+'/apps'],stdin=f,check=True)
            install();subprocess.run(['docker','restart',CONTAINER],check=True,stdout=subprocess.DEVNULL)
        except Exception:
            raise RuntimeError('Upgrade and code rollback failed; inspect private evidence; do not reset database') from None
        raise RuntimeError('Upgrade failed; prior app code/package restored; inspect private evidence') from None
    print(json.dumps({'installed_version':'0.3.1','protected_records_unchanged':True,'schema_migration':False,'evidence':str(evidence)}))


if __name__=='__main__':
    a=argparse.ArgumentParser(description=__doc__);a.add_argument('environment',type=Path);a.add_argument('--apply',action='store_true')
    args=a.parse_args();run(args.environment,args.apply)
