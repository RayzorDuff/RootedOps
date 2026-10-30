#!/usr/bin/env python3
"""Fresh-host full-stack test preparation for #22. Never reads production .env."""
import argparse
import base64
import copy
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import socket
import subprocess
import time
import yaml

ROOT=Path(__file__).resolve().parents[1]
RALLLY_REV='26927f4703b8b72f7df2947756e6a04ea9360f9b'
# The templates remain -test; generated hostnames come from the deployment suffix.
DEFAULT_HOSTS={'erpnext':'erp-test.danks.store','appsmith':'appsmith-test.danks.store',
 'n8n':'n8n-test.danks.store','nocodb':'nocodb-test.danks.store',
 'documenso':'documenso-test.danks.store','listmonk':'listmonk-test.danks.store',
 'librechat':'ai-test.danks.store','kids-ai':'kids-ai-test.danks.store',
 'qr':'qr-test.danks.store','dank-wordpress':'shop-test.danks.store',
 'rootedpsyche-wordpress':'www-test.rootedpsyche.org',
 'tymeslot':'schedule-test.rootedpsyche.org','rallly':'poll-test.rootedpsyche.org'}
HOSTS=DEFAULT_HOSTS.copy()


def hosts_for_suffix(suffix):
    if suffix and not re.fullmatch(r'-[a-z0-9]+(?:-[a-z0-9]+)*',suffix):
        raise ValueError('Hostname suffix must be empty or begin with - followed by lowercase letters/digits')
    return {name:host.replace('-test.',suffix+'.',1) for name,host in DEFAULT_HOSTS.items()}


def deployment_hosts(output):
    receipt=json.loads((output/'receipt.json').read_text())
    return hosts_for_suffix(receipt.get('hostname_suffix','-test'))

EXTERNAL=('ECWID_','CLOVER_','AIRTABLE_','REPORT_','GIVEBUTTER_','ERPNEXT_API_',
 'DOCUMENSO_API_TOKEN','NOCODB_API_TOKEN','LISTMONK_API_TOKEN','OPENROUTER_KEY','GITHUB_MCP_TOKEN',
 'TYMESLOT_GOOGLE_','SIGNATUREGATE_PAPER_DRIVE_FOLDER_ID')


def private_write(path,text):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as stream:stream.write(text)


def template():
    # Template parsing is literal; never source a downloaded backup as shell code.
    values={}
    for line in (ROOT/'.env.example').read_text().splitlines():
        if line and not line.startswith('#') and '=' in line:
            key,value=line.split('=',1);values[key]=value.strip('"')
    return values


def environment():
    env=template()
    for key in env:
        if any(term in key for term in ('PASSWORD','SECRET','TOKEN','ENCRYPTION','CREDS_')):
            env[key]=secrets.token_hex(32 if not key.endswith('_IV') else 16)
        if key.startswith(EXTERNAL):env[key]=''
    env.update(NC_PUBLIC_URL='https://'+HOSTS['nocodb'],ERPNEXT_INSTALL_COMMERCE='1',
       MP_BRIDGE_DB_NAME='mushroomprocess_test',MP_BRIDGE_DB_USER='mushroomprocess_test',
       ERPNEXT_SITE_NAME=HOSTS['erpnext'],ERPNEXT_PUBLIC_URL='https://'+HOSTS['erpnext'],
       N8N_HOST=HOSTS['n8n'],N8N_EDITOR_BASE_URL='https://'+HOSTS['n8n']+'/',
       WEBHOOK_URL='https://'+HOSTS['n8n']+'/',TYMESLOT_PUBLIC_HOST=HOSTS['tymeslot'],
       TYMESLOT_ENABLE_GOOGLE_AUTH='false',COMPOSE_PROFILES='',
       SCHEDULING_SMTP_USER='test@example.invalid',SCHEDULING_SMTP_PASSWORD=secrets.token_hex(16),
       DOCUMENSO_SMTP_HOST='mailpit',DOCUMENSO_SMTP_PORT='1025',DOCUMENSO_SMTP_USERNAME='',
       DOCUMENSO_SMTP_PASSWORD='',DOCUMENSO_SMTP_FROM_ADDRESS='test@example.invalid')
    env['TYMESLOT_SECRET_KEY_BASE']=base64.b64encode(secrets.token_bytes(64)).decode()
    env['TYMESLOT_DATA_ENCRYPTION_KEY']=base64.b64encode(secrets.token_bytes(32)).decode()
    return env


def upstream(path):
    if not path.exists():
        subprocess.run(['git','clone','https://github.com/lukevella/rallly-selfhosted.git',str(path)],check=True)
        subprocess.run(['git','-C',str(path),'checkout','--detach',RALLLY_REV],check=True)
    actual=subprocess.check_output(['git','-C',str(path),'rev-parse','HEAD'],text=True).strip()
    if actual!=RALLLY_REV:raise ValueError('Unexpected Rallly revision; use the pinned upstream checkout')


def transform(config,source, project):
    config=copy.deepcopy(config);config['name']=project
    config.pop('x-erpnext-image',None)
    config['networks']={'default':{'internal':True}}
    for name,service in list(config['services'].items()):
        # Compose may tokenize multiline initializer commands during rendering.
        # Bash must receive the entire script as its single -lc argument.
        if name in ('erpnext-apps-init','erpnext-configurator'):
            if service.get('entrypoint')!=['bash','-lc']:
                raise ValueError('Unexpected ERP initializer entrypoint: '+name)
            cmd=service.get('command')
            script=cmd if isinstance(cmd,str) else cmd[0] if isinstance(cmd,list) and len(cmd)==1 and isinstance(cmd[0],str) else None
            if not script or not script.strip():
                raise ValueError('Expected one ERP initializer script: '+name)
            service['entrypoint']=['bash','-lc',script]
            service['command']=[]
        service.pop('container_name',None)
        service.pop('labels',None)
        if isinstance(service.get('environment'),dict):
            service['environment']={k:('true' if v is True else 'false' if v is False else v) for k,v in service['environment'].items()}
        if 'build' in service:
            build=service['build'];build['context']=str((source/str(build['context'])).resolve())
        ports=[]
        for port in service.get('ports',[]):
            port=str(port)
            if not port.startswith('127.0.0.1:'):port='127.0.0.1:'+port
            ports.append(port)
        if ports:service['ports']=ports
        mounts=[]
        for mount in service.get('volumes',[]):
            if isinstance(mount,str):
                parts=mount.split(':')
                if parts[0].startswith('.'):
                    parts[0]=str((source/parts[0]).resolve())
                    mount=':'.join(parts)
                mounts.append(mount)
            else:
                if mount.get('type')=='bind' and str(mount.get('source','')).startswith('.'):
                    mount['source']=str((source/mount['source']).resolve())
                mounts.append(mount)
        if mounts:service['volumes']=mounts
    return config


def prepare(output,rallly_path=None,hostname_suffix="-test"):
    global HOSTS
    HOSTS=hosts_for_suffix(hostname_suffix)
    output=output.resolve()
    if output.exists():raise ValueError('Destination exists; never overwrite test credentials')
    if (ROOT/'.env').exists():raise ValueError('Use a clean checkout without a runtime .env')
    # Fail before writing credentials if required source/build context disappeared.
    required=['docker/documenso.Dockerfile','docker/erpnext-custom.Dockerfile',
              'erpnext/apps/rootedops_commerce/pyproject.toml','backup/restore-stack.sh']
    for name in required:
        if not (ROOT/name).is_file():raise ValueError('Missing source dependency: '+name)
    rallly_path=(rallly_path or ROOT/'docker/scheduling/rallly-selfhosted').resolve()
    upstream(rallly_path)
    env=environment()
    output.mkdir(parents=True,mode=0o700)
    private_write(output/'.env','\n'.join(k+'='+str(v) for k,v in env.items())+'\n')
    private_write(output/'TEST_ENVIRONMENT','rootedops-full-test\n')
    certs=output/'certs';certs.mkdir(mode=0o700)
    secret_env=dict(os.environ,DOCUMENSO_TEST_SIGNING_PASSWORD=env['DOCUMENSO_SIGNING_PASSPHRASE'])
    subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(certs/'test.key'),'-out',str(certs/'test.crt'),'-days','30','-subj','/CN=RootedOps TEST ONLY'],check=True,capture_output=True)
    subprocess.run(['openssl','pkcs12','-export','-out',str(certs/'cert.p12'),'-inkey',str(certs/'test.key'),'-in',str(certs/'test.crt'),'-passout','env:DOCUMENSO_TEST_SIGNING_PASSWORD'],env=secret_env,check=True,capture_output=True)
    # Parent is private; allow the container's unprivileged UID to read the mounted P12.
    (certs/'cert.p12').chmod(0o644)
    private_write(output/'DOCUMENSO_CERT_READY','TEST signing certificate only; never production legal signatures.\n')
    os.symlink(output/'.env',ROOT/'.env')
    sources=[('core',ROOT/'docker/docker-compose.yml','rootedops-full-test'),
             ('rootedpsyche',ROOT/'docker/docker-compose.wordpress.yml','rootedpsyche-test'),
             ('dank',ROOT/'docker/docker-compose.dank-wordpress.yml','dank-store-test'),
             ('tymeslot',ROOT/'docker/scheduling/tymeslot.compose.yml','tymeslot-test')]
    for name,path,project in sources:
        config=transform(yaml.safe_load(path.read_text()),path.parent,project)
        if name=='core':
            # Issue #22: use the pinned upstream release image; building floating main
            # under the legacy Node 20 Dockerfile breaks on upstream Node/npm changes.
            config['services']['documenso'].pop('build',None)
            config['services']['documenso']['image']='ghcr.io/documenso/documenso:v2.20.0'
            config['services']['documenso']['volumes'][0]=str(output/'certs/cert.p12')+':/opt/documenso/cert.p12:ro'
            config['services'].pop('minecraft-bedwars',None) # explicit off; no automatic world creation
            config['services']['mailpit']={'image':'axllent/mailpit:v1.27','restart':'unless-stopped'}
        if name=='core':
            config['services']['erpnext-db']['healthcheck']['test']=['CMD-SHELL','healthcheck.sh --connect --innodb_initialized']
        if name=='tymeslot':
            config['services']['tymeslot']['environment'].update(SMTP_HOST='mailpit',SMTP_PORT='1025')
            config['services']['mailpit']={'image':'axllent/mailpit:v1.27','restart':'unless-stopped'}
        private_write(output/(name+'.yml'),yaml.safe_dump(config,sort_keys=False))
    # Rallly keeps its own credential file and pinned upstream compose/config.
    rallly=output/'rallly';rallly.mkdir(mode=0o700)
    r_env={'DOMAIN':HOSTS['rallly'],'PROXY_MODE':'external','WEB_PORT':'127.0.0.1:3003',
        'SECRET_PASSWORD':secrets.token_hex(32),'POSTGRES_PASSWORD':secrets.token_hex(32),
        'S3_ACCESS_KEY_ID':'GK'+secrets.token_hex(12),'S3_SECRET_ACCESS_KEY':secrets.token_hex(32),
        'GARAGE_RPC_SECRET':secrets.token_hex(32),'SMTP_HOST':'mailpit','SMTP_PORT':'1025',
        'SMTP_SECURE':'false','SMTP_USER':'test@example.invalid','SMTP_PWD':'',
        'POSTGRES_VERSION':'18','POSTGRES_DATA_MOUNT':'/var/lib/postgresql'}
    private_write(rallly/'.env','\n'.join(k+'='+v for k,v in r_env.items())+'\n')
    config=transform(yaml.safe_load((rallly_path/'docker-compose.yml').read_text()),rallly_path,'rallly-test')
    config['services'].pop('traefik',None)
    config['volumes'].pop('acme-data',None)
    config['services']['web']['env_file']=[str(rallly/'.env')]
    config['services']['web']['ports']=['127.0.0.1:3003:3000']
    config['services']['mailpit']={'image':'axllent/mailpit:v1.27','restart':'unless-stopped'}
    private_write(rallly/'compose.yml',yaml.safe_dump(config,sort_keys=False))
    receipt={'schema_version':1,'source_commit':subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip(),
       'mode':'isolated-full-test','hostname_suffix':hostname_suffix,'hosts':HOSTS,'rallly_revision':RALLLY_REV,'minecraft':'disabled',
       'outbound':'internal Docker networks; no production SMTP/OAuth/payment credentials',
       'acceptance':'pending operator clean-host startup, restore and reboot validation'}
    private_write(output/'receipt.json',json.dumps(receipt,indent=2)+'\n')
    private_write(output/'README.txt','Issue #22 full-stack TEST configuration.\nNo services started. Credentials are private.\nRun: python3 scripts/host_recovery.py validate '+str(output)+'\nThen: python3 scripts/host_recovery.py start '+str(output)+'\nExternal integrations require operator configuration; see doc/fresh-host-recovery.md.\n')
    print('Prepared full-stack test configuration; no credentials printed or services started.')


def projects(output):
    for name in ('core','rootedpsyche','dank','tymeslot'):
        yield output/'.env',output/(name+'.yml'),[]
    yield output/'rallly/.env',output/'rallly/compose.yml',['--profile','bundled-db','--profile','bundled-storage']


def command(env,path,profiles):return ['docker','compose','--env-file',str(env),'-f',str(path),*profiles]


def validate(output):
    if (output/'TEST_ENVIRONMENT').read_text().strip()!='rootedops-full-test':raise ValueError('Not a test environment')
    used=set()
    for env,path,profiles in projects(output):
        config=yaml.safe_load(path.read_text())
        if config.get('networks',{}).get('default',{}).get('internal') is not True:raise ValueError('External egress forbidden')
        for service in config['services'].values():
            for port in service.get('ports',[]):
                if not str(port).startswith('127.0.0.1:'):raise ValueError('Non-loopback port')
        # Docker performs exact interpolation/format validation without printing secrets.
        subprocess.run(command(env,path,profiles)+['config','--quiet'],check=True)
        resolved=json.loads(subprocess.check_output(command(env,path,profiles)+['config','--format','json']))
        for service in resolved['services'].values():
            entrypoint=service.get('entrypoint') or []
            if entrypoint[:2]==['bash','-lc']:
                # Accepted forms: one shell script in argv[2] with no command,
                # or a two-item entrypoint with a one-element command.
                cmd=service.get('command',[])
                valid=(len(entrypoint)==3 and isinstance(entrypoint[2],str) and not cmd) or (len(entrypoint)==2 and len(cmd)==1)
                if not valid:raise ValueError('Shell initializer must receive exactly one script argument')
            for port in service.get('ports',[]):
                key=(port.get('protocol','tcp'),port['published'])
                if key in used:raise ValueError('Duplicate host port: '+str(key))
                used.add(key)
                sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM if key[0]=='udp' else socket.SOCK_STREAM)
                try:sock.bind(('127.0.0.1',int(key[1])))
                finally:sock.close()
            for mount in service.get('volumes',[]):
                if mount['type']=='bind':
                    source=Path(mount['source'])
                    # Explicit setup paths; don't let Docker create a directory in place of cert/config files.
                    if not source.exists() and (source.suffix or source.name.endswith('certs')):
                        raise ValueError('Missing bind source: '+str(source))
    print('Compose interpolation, isolation, unique/available ports and bind sources validated.')


def start(output):
    validate(output)
    if not (output/'DOCUMENSO_CERT_READY').exists():raise ValueError('Generate the test signing certificate before startup; see runbook')
    # Builds occur before any application initialization. Heavy full-stack builds need capacity.
    env,path,profiles=next(projects(output))
    subprocess.run(command(env,path,profiles)+['build'],check=True)
    core=command(env,path,profiles)
    subprocess.run(core+['up','-d','erpnext-db','erpnext-redis-cache','erpnext-redis-queue'],check=True)
    for _ in range(120):
        cid=subprocess.check_output(core+['ps','-q','erpnext-db'],text=True).strip()
        if cid and subprocess.check_output(['docker','inspect','-f','{{.State.Health.Status}}',cid],text=True).strip()=='healthy':break
        time.sleep(2)
    else:raise RuntimeError('ERP MariaDB readiness failed; applications were not started')
    for service in ('erpnext-apps-init','erpnext-configurator'):
        subprocess.run(core+['run','--rm','--no-deps',service],check=True)
    subprocess.run(core+['--profile','erpnext-init','run','--rm','erpnext-bootstrap'],check=True)
    for env,path,profiles in projects(output):
        subprocess.run(command(env,path,profiles)+['up','-d'],check=True)
    status(output)
    print('Startup commands completed. Verify application setup, health and reboot receipt before acceptance.')


def dns(expected,exports,live=False,hosts=None):
    ipaddress.ip_address(expected)
    addresses={}
    for path in exports:
        for line in path.read_text().splitlines():
            m=re.match(r'^(\S+)\s+\d+\s+IN\s+(A|AAAA)\s+(\S+)',line)
            if m:addresses.setdefault(m[1].rstrip('.'),[]).append(m[3])
    report={host:{'export_addresses':addresses.get(host,[]),'matches_expected':addresses.get(host)==[expected]} for host in (hosts or HOSTS).values()}
    if live:
        for host,row in report.items():
            try:current=sorted({a[4][0] for a in socket.getaddrinfo(host,None,type=socket.SOCK_STREAM)})
            except socket.gaierror:current=[]
            row['live_addresses']=current
            row['matches_expected']=current==[expected]
    print(json.dumps(report,indent=2))
    return all(r['matches_expected'] for r in report.values())


def status(output):
    result={'projects':{},'manual_checks':['authenticated setup','data inventories','host reboot','restore round-trip']}
    for env,path,profiles in projects(output):
        rows=subprocess.check_output(command(env,path,profiles)+['ps','--all','--format','json'],text=True).strip()
        try:data=json.loads(rows) if rows else []
        except json.JSONDecodeError:data=[json.loads(line) for line in rows.splitlines()]
        if isinstance(data,dict):data=[data]
        result['projects'][path.stem]=[{k:row.get(k) for k in ('Service','State','Health','ExitCode')} for row in data]
    path=output/'startup-receipt.json'
    temporary=path.with_suffix('.new');private_write(temporary,json.dumps(result,indent=2)+'\n');temporary.replace(path)
    print(json.dumps(result,indent=2))


def publish(output,expected,email,confirmed):
    if not confirmed:raise ValueError('Configure initial accounts through SSH tunnels before publishing')
    hosts=deployment_hosts(output)
    if not dns(expected,[],live=True,hosts=hosts):raise ValueError('All live A/AAAA records must match the new test host before TLS')
    for name in hosts:
        source=ROOT/'nginx'/(name+'.conf')
        if name=='dank-wordpress':source=ROOT/'nginx/dank-wordpress.conf'
        if name=='librechat':source=ROOT/'nginx/librechat.conf'
        if name=='kids-ai':source=ROOT/'nginx/kids-ai.conf'
        if not source.exists():raise ValueError('Missing vhost: '+str(source))
        destination=Path('/etc/nginx/sites-available')/source.name
        if destination.exists():raise ValueError('Do not overwrite installed vhosts: '+str(destination))
    import shutil
    for name in hosts:
        source=ROOT/'nginx'/(name+'.conf')
        destination=Path('/etc/nginx/sites-available')/source.name
        rendered=source.read_text()
        for key,default_host in DEFAULT_HOSTS.items():
            rendered=rendered.replace(default_host,hosts[key])
        destination.write_text(rendered)
        (Path('/etc/nginx/sites-enabled')/source.name).symlink_to(destination)
    subprocess.run(['nginx','-t'],check=True)
    subprocess.run(['systemctl','reload','nginx'],check=True)
    args=['certbot','--nginx','--non-interactive','--agree-tos','--email',email,'--redirect']
    for host in hosts.values():args+=['-d',host]
    subprocess.run(args,check=True)
    subprocess.run(['certbot','renew','--dry-run'],check=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='action',required=True)
    for action in ('prepare','validate','start','status'):
        q=s.add_parser(action);q.add_argument('output',type=Path)
    q=s.add_parser('dns');q.add_argument('--deployment',type=Path,default=ROOT/'.test-deployment');q.add_argument('--expected-ip',required=True);q.add_argument('exports',nargs='*',type=Path);q.add_argument('--live',action='store_true')
    q=s.add_parser('publish');q.add_argument('output',type=Path);q.add_argument('--expected-ip',required=True);q.add_argument('--email',required=True);q.add_argument('--accounts-configured',action='store_true')
    s.choices['prepare'].add_argument('--hostname-suffix',default='-test')
    a=p.parse_args()
    if a.action=='dns':raise SystemExit(0 if dns(a.expected_ip,a.exports,a.live,hosts=deployment_hosts(a.deployment.resolve())) else 1)
    if a.action=='publish':publish(a.output.resolve(),a.expected_ip,a.email,a.accounts_configured)
    elif a.action=='prepare':prepare(a.output.resolve(),hostname_suffix=a.hostname_suffix)
    else:globals()[a.action](a.output.resolve())
