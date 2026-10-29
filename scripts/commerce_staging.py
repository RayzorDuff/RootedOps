#!/usr/bin/env python3
"""Render a minimal isolated Compose project from the reviewed RootedOps services.

Requires PyYAML. Refuses overwrites; writes secrets locally with mode 0600.
Run from a fresh checkout; production .env is never read.
"""
import argparse
import os
from pathlib import Path
import re
import secrets
import yaml

ROOT = Path(__file__).resolve().parents[1]
ERP = ['erpnext-db','erpnext-redis-cache','erpnext-redis-queue','erpnext-apps-init',
       'erpnext-configurator','erpnext-backend','erpnext-websocket','erpnext-queue-short',
       'erpnext-queue-long','erpnext-scheduler','erpnext-frontend','erpnext-bootstrap']
SERVICES = ['mushroomprocess-bridge-postgres','n8n','appsmith'] + ERP


def render(output):
    output = output.resolve()
    if output.exists():
        raise ValueError('Destination must not exist; never overwrite credentials')
    base = yaml.safe_load((ROOT/'docker/docker-compose.yml').read_text())
    services = {name:base['services'][name] for name in SERVICES}
    volumes = {}
    for name, service in services.items():
        service.pop('container_name',None)
        for mount in service.get('volumes',[]):
            src = mount.split(':')[0]
            if src.startswith('.'):
                # The source compose lives in docker/; rendered file lives elsewhere.
                index = service['volumes'].index(mount)
                service['volumes'][index] = str((ROOT/'docker'/src).resolve()) + mount[len(src):]
            else:
                volumes[src] = base.get('volumes',{}).get(src)
        if 'build' in service:
            service['build']['context'] = str(ROOT)
        if 'ports' in service:
            service['ports'] = ['127.0.0.1:'+str(p) for p in service['ports']]
        # Keep Frappe bootstrap/configurator, but no unrelated infrastructure.
        deps = service.get('depends_on',[])
        if isinstance(deps,list):service['depends_on']=[d for d in deps if d in services]
    services['erpnext-bootstrap']['environment']['ERPNEXT_INSTALL_COMMERCE'] = '1'
    # Apps volume is fresh here. No modifications to existing production volumes.
    config = {'name':'commerce-test','services':services,'volumes':volumes}
    env = {}
    for line in (ROOT/'.env.example').read_text().splitlines():
        if '=' in line and not line.startswith('#'):
            k,v=line.split('=',1);env[k]=v
    for k in env:
        if any(term in k for term in ('PASSWORD','SECRET','TOKEN','ENCRYPTION_KEY')):
            env[k] = secrets.token_hex(24)
    env.update(ERPNEXT_SITE_NAME='erp-test.danks.store',ERPNEXT_PUBLIC_URL='https://erp-test.danks.store',
        ERPNEXT_HTTP_PORT='8085',MP_BRIDGE_DB_NAME='mushroomprocess_test',MP_BRIDGE_DB_USER='mushroomprocess_test',
        N8N_HOST='n8n-test.danks.store',N8N_PROTOCOL='https',N8N_PORT='5678',
        WEBHOOK_URL='https://n8n-test.danks.store/',N8N_EDITOR_BASE_URL='https://n8n-test.danks.store/',
        N8N_SECURE_COOKIE='true',ERPNEXT_INSTALL_COMMERCE='1')
    # No upstream production service URLs/tokens are necessary in this project.
    for k in list(env):
        if k.startswith(('LISTMONK_','DOCUMENSO_','SIGNATUREGATE_','AIRTABLE_','NC_')):
            env[k] = ''
    output.mkdir(mode=0o700,parents=True)
    for name,text in [('compose.yml',yaml.safe_dump(config,sort_keys=False)),('.env','\n'.join(k+'='+str(v) for k,v in env.items())+'\n')]:
        path=output/name
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as f:f.write(text)
    print('Created isolated configuration; credentials were not printed.')

if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);a=p.parse_args();render(a.output)
