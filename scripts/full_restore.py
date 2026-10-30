#!/usr/bin/env python3
"""Fresh-host full or selected commerce restore; internal test networks only."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import time
import yaml
from host_recovery import ROOT,projects,command
from commerce_restore import read_env,copy_counts

# Archive names are stable even though destination Compose project names differ.
VOLUMES=[('core','nocodb','/usr/app/data','nocodb_data.tgz'),
 ('core','n8n','/home/node/.n8n','n8n_data.tgz'),
 ('core','appsmith','/appsmith-stacks','appsmith_stacks.tgz'),
 *[('core','erpnext-backend','/home/frappe/frappe-bench/'+kind,'erpnext_'+kind+'.tgz') for kind in ('sites','apps','logs')],
 ('core','erpnext-redis-cache','/data','erpnext_redis_cache_data.tgz'),
 ('core','erpnext-redis-queue','/data','erpnext_redis_queue_data.tgz'),
 ('rootedpsyche','rootedpsyche-wordpress','/var/www/html','rootedpsyche-wordpress-html.tgz'),
 ('dank','dank-wordpress','/var/www/html','dank-wordpress-html.tgz'),
 ('tymeslot','tymeslot','/app/data','rootedops-scheduling_tymeslot_data.tgz'),
 ('tymeslot','tymeslot','/var/lib/postgresql/data','rootedops-scheduling_tymeslot_pg.tgz'),
 ('rallly','db',None,'rallly-selfhosted_db-data.tgz'),
 ('rallly','garage','/var/lib/garage/meta','rallly-selfhosted_garage-meta.tgz'),
 ('rallly','garage','/var/lib/garage/data','rallly-selfhosted_garage-data.tgz')]
for kind in ('','-kids'):
 for service,target,archive in [('librechat'+kind+'-mongodb','/data/db','mongodb'),
   ('librechat'+kind,'/app/data','data'),('librechat'+kind,'/app/uploads','uploads'),
   ('librechat'+kind,'/app/api/logs','logs')]:
  VOLUMES.append(('core',service,target,'librechat'+kind+'-'+archive+'.tgz'))
PG=[('signaturegate-postgres','SIG'),('mushroomprocess-bridge-postgres','MP_BRIDGE'),
 ('listmonk-postgres','LISTMONK'),('nocodb-meta-postgres','NC'),('documenso-postgres','DOCUMENSO')]
LOCAL_KEYS=('N8N_ENCRYPTION_KEY','APPSMITH_ENCRYPTION_PASSWORD','APPSMITH_ENCRYPTION_SALT',
 'TYMESLOT_DATA_ENCRYPTION_KEY','TYMESLOT_SECRET_KEY_BASE','TYMESLOT_GOOGLE_STATE_SECRET',
 'LIBRECHAT_CREDS_KEY','LIBRECHAT_CREDS_IV','LIBRECHAT_KIDS_CREDS_KEY','LIBRECHAT_KIDS_CREDS_IV',
 'DOCUMENSO_ENCRYPTION_KEY','DOCUMENSO_ENCRYPTION_SECONDARY_KEY','DOCUMENSO_SIGNING_PASSPHRASE','NC_AUTH_JWT_SECRET')

COMMERCE_COMPONENTS=('mushroomprocess','erpnext','appsmith','n8n','dank-wordpress')
COMPONENT_FILES={
 'mushroomprocess':{'mushroomprocess-bridge-postgres.sql.gz'},
 'erpnext':{'erpnext-all-databases.sql.gz','erpnext_sites.tgz','erpnext_apps.tgz'},
 'appsmith':{'appsmith_stacks.tgz'},'n8n':{'n8n_data.tgz'},
 'dank-wordpress':{'dank-wordpress-all-databases.sql.gz','dank-wordpress-html.tgz'}}
COMPONENT_KEYS={'appsmith':{'APPSMITH_ENCRYPTION_PASSWORD','APPSMITH_ENCRYPTION_SALT'},
 'n8n':{'N8N_ENCRYPTION_KEY'}}
REMOVABLE_SECRET_METADATA={'meta/.env','bind_mounts/rallly-selfhosted-env.tgz'}


def write_env(path,values):
    temporary=path.with_suffix('.new')
    fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f:
        for k,v in values.items():
            # Compose dotenv supports single-quoted literal values; reject multiline records.
            if '\n' in v or '\r' in v:raise ValueError('Multiline secret requires manual configuration')
            f.write(k+"='"+v.replace("'","\\'")+"'\n")
    temporary.replace(path)


class Recovery:
 def __init__(self,output,backup,components=None,key_file=None,allow_removed_secret_metadata=False):
    self.output,self.backup=output.resolve(),backup.resolve()
    self.components=None if components is None else frozenset(components)
    if self.components is not None and (not self.components or not self.components<=set(COMMERCE_COMPONENTS)):
        raise ValueError('Select supported commerce components explicitly')
    self.selected_files=None if self.components is None else set().union(*(COMPONENT_FILES[c] for c in self.components))
    self.key_file=Path(key_file) if key_file is not None else None
    self.allow_removed_secret_metadata=allow_removed_secret_metadata
    self.removed_secret_metadata=[]
    if self.components is None and (self.key_file or allow_removed_secret_metadata):
        raise ValueError('Secret-minimal options require an explicit component selection')
    self.commands={name:command(self.output/'.env',self.output/(name+'.yml'),[]) for name in ('core','rootedpsyche','dank','tymeslot')}
    self.commands['rallly']=command(self.output/'rallly/.env',self.output/'rallly/compose.yml',['--profile','bundled-db','--profile','bundled-storage'])
 def selected(self,archive):return self.selected_files is None or archive in self.selected_files
 def archives(self,directory,suffix):
    return [p for p in (self.backup/directory).glob(suffix) if self.selected(p.name)]
 def bind_archives(self):
    # Commerce restores no production routing, scheduling secrets or unrelated binds.
    return list((self.backup/'bind_mounts').glob('*.tgz')) if self.components is None else []
 def encryption_source(self):
    if self.components is None:return read_env(self.backup/'meta/.env')
    needed=set().union(*(COMPONENT_KEYS.get(c,set()) for c in self.components))
    if not needed:return {}
    if self.key_file is None:raise ValueError('Provide a private --key-file with only selected original encryption keys')
    if self.key_file.stat().st_mode&0o077:raise ValueError('Encryption key file must have private permissions')
    source=read_env(self.key_file)
    if set(source)!=needed or any(not value for value in source.values()):
        raise ValueError('Key file must contain exactly the selected encryption keys, without other production credentials')
    return source
 def verify_checksums(self):
    if not self.allow_removed_secret_metadata:
        subprocess.run(['sha256sum','--check','--quiet','SHA256SUMS'],cwd=self.backup,check=True)
        return
    # Never rewrite the original manifest or ignore arbitrary missing payloads.
    self.removed_secret_metadata=[];verified=0;seen=set()
    for line in (self.backup/'SHA256SUMS').read_text().splitlines():
        match=re.fullmatch(r'([a-fA-F0-9]{64}) [ *](.+)',line)
        if not match:raise ValueError('Invalid checksum manifest entry')
        name=match[2];parts=Path(name)
        if parts.is_absolute() or '..' in parts.parts:raise ValueError('Unsafe checksum path')
        normalized=parts.as_posix()
        if normalized in seen:raise ValueError('Duplicate checksum path')
        seen.add(normalized);path=self.backup/parts
        if not path.exists() and normalized in REMOVABLE_SECRET_METADATA:
            self.removed_secret_metadata.append(normalized);continue
        if not path.is_file() or not path.resolve().is_relative_to(self.backup):raise ValueError('Missing or unsafe backup payload')
        digest=hashlib.sha256()
        with path.open('rb') as stream:
            while block:=stream.read(1024*1024):digest.update(block)
        if digest.hexdigest()!=match[1].lower():raise ValueError('Backup checksum mismatch')
        verified+=1
    expected={('db/' if name.endswith('.sql.gz') else 'volumes/')+name for name in self.selected_files}
    if not verified or not expected<=seen:raise ValueError('Selected payload missing from checksum manifest')
 def dc(self,project,*args,**kw):
    try:return subprocess.run(self.commands[project]+list(args),check=True,**kw)
    except subprocess.CalledProcessError:
        # Compose exec arguments may contain generated DB credentials. Never put
        # the original command/exception into a traceback or public report.
        raise RuntimeError('Recovery command failed in '+project+'; inspect private service diagnostics') from None
 def preflight(self,source_site=None):
    if (self.output/'TEST_ENVIRONMENT').read_text().strip()!='rootedops-full-test':raise ValueError('Explicit full-test environment required')
    if (self.output/'RESTORE_STARTED').exists():raise ValueError('Restore already started; inspect partial state instead of retrying')
    if not (self.backup/'SHA256SUMS').is_file():raise ValueError('Full restore requires SHA256SUMS')
    if self.selected_files is not None:
        for archive in sorted(self.selected_files):
            directory='db' if archive.endswith('.sql.gz') else 'volumes'
            if not (self.backup/directory/archive).is_file():raise ValueError('Missing selected backup: '+archive)
    if self.selected('erpnext-all-databases.sql.gz') and (self.backup/'db/erpnext-all-databases.sql.gz').exists():
        if not source_site or not re.fullmatch(r'[a-zA-Z0-9.-]+',source_site):raise ValueError('--source-site required before restoring ERP')
    self.verify_checksums()
    if subprocess.check_output(['docker','ps','-aq'],text=True).strip():
        raise ValueError('Full recovery requires a new host without existing containers')
    for _,path,_ in projects(self.output):
        config=yaml.safe_load(path.read_text())
        if config['networks']['default'].get('internal') is not True:raise ValueError('Outbound isolation required')
        if any(s.get('container_name') for s in config['services'].values()):raise ValueError('Explicit container names forbidden')
        if any(v for v in config.get('volumes',{}).values()):raise ValueError('External/named shared volumes forbidden')
        if any(not str(p).startswith('127.0.0.1:') for s in config['services'].values() for p in s.get('ports',[])):raise ValueError('Loopback ports required')
        project=config['name']
        for kind in ('container','volume'):
            cmd=['docker','ps','-aq','--filter','label=com.docker.compose.project='+project] if kind=='container' else ['docker','volume','ls','-q','--filter','label=com.docker.compose.project='+project]
            if subprocess.check_output(cmd,text=True).strip():raise ValueError('Existing test project; refusing destructive reuse')
    if not (self.output/'IMAGE_COMPATIBILITY_REVIEWED').is_file():raise ValueError('Review backup app/image versions first; create IMAGE_COMPATIBILITY_REVIEWED only after compatibility is confirmed')
    if self.components is None and not (self.backup/'meta/.env').is_file():raise ValueError('Source local encryption keys are required in meta/.env')
    for path in self.archives('volumes','*.tgz'):
        subprocess.run(['bash','-c','source "$1"; validate_managed_volume_archive "$2"','preflight',str(ROOT/'backup/volume-tools.sh'),str(path)],check=True)
    known={v[3] for v in VOLUMES}
    extra={p.name for p in self.archives('volumes','*.tgz')}-known
    if extra:raise ValueError('Unmapped archives require explicit recovery mapping: '+', '.join(sorted(extra)))
    known_db={service+'.sql.gz' for service,_ in PG}|{'erpnext-all-databases.sql.gz','rootedpsyche-wordpress-all-databases.sql.gz','dank-wordpress-all-databases.sql.gz'}
    extra_db={p.name for p in self.archives('db','*.gz')}-known_db
    if extra_db:raise ValueError('Unmapped database dumps: '+', '.join(sorted(extra_db)))
    source=self.encryption_source()
    if self.selected('n8n_data.tgz') and (self.backup/'volumes/n8n_data.tgz').exists() and not source.get('N8N_ENCRYPTION_KEY'):
        raise ValueError('Missing original n8n encryption key')
    if self.components is not None:
        for component in self.components:
            if any(not source.get(k) for k in COMPONENT_KEYS.get(component,())):
                raise ValueError('Missing original encryption keys for '+component)
    scheduling=[p.name for p in self.archives('volumes','*.tgz') if p.name.startswith(('rootedops-scheduling_','rallly-selfhosted_'))]
    if scheduling and len(scheduling)!=5:raise ValueError('Incomplete scheduling backup')
    if scheduling and not (self.backup/'bind_mounts/rallly-selfhosted-env.tgz').is_file():raise ValueError('Missing Rallly credentials')
    for path in self.archives('db','*.gz'):

        with gzip.open(path,'rb') as stream:
            while stream.read(1024*1024):pass
    # Validate bind archives too, before *any* mutation.
    for path in self.bind_archives():
        subprocess.run(['bash','-c','source "$1"; validate_volume_archive "$2"','preflight',str(ROOT/'backup/volume-tools.sh'),str(path)],check=True)
 def volume(self,project,service,destination,archive):
    self.dc(project,'up','--no-start','--no-deps',service)
    cid=self.dc(project,'ps','-a','-q',service,capture_output=True,text=True).stdout.strip()
    mounts=json.loads(subprocess.check_output(['docker','inspect','-f','{{json .Mounts}}',cid],text=True))
    matches=[m for m in mounts if m['Type']=='volume' and (m['Destination']==destination if destination else m['Destination'].startswith('/var/lib/postgresql'))]
    if len(matches)!=1:raise ValueError('Ambiguous target volume')
    subprocess.run(['docker','run','--rm','--network','none','-v',matches[0]['Name']+':/target','-v',str(self.backup/'volumes')+':/backup:ro','alpine:3.20','sh','-ec',
     'find /target -mindepth 1 -maxdepth 1 -exec rm -rf {} +; tar -xzf "/backup/$1" -C /target','restore',archive],check=True)
 def sql(self,project,file,args):
    with gzip.open(self.backup/'db'/file,'rb') as f:
        proc=subprocess.Popen(self.commands[project]+args,stdin=subprocess.PIPE)
        try:
            while block:=f.read(1024*1024):proc.stdin.write(block)
            proc.stdin.close()
            if proc.wait():raise RuntimeError('SQL restore failed')
        finally:
            if proc.poll() is None:proc.terminate();proc.wait()
 def ready(self,project,service):
    for _ in range(120):
        cid=self.dc(project,'ps','-q',service,capture_output=True,text=True).stdout.strip()
        if cid:
            state=json.loads(subprocess.check_output(['docker','inspect','-f','{{json .State}}',cid],text=True))
            if state.get('Status')=='running':
                health=state.get('Health')
                if health is not None:
                    if health.get('Status')=='healthy':return
                elif service.endswith('postgres') and subprocess.run(
                    ['docker','exec',cid,'pg_isready','-q'],stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,check=False).returncode==0:
                    return
        time.sleep(2)
    raise RuntimeError('Readiness timed out: '+service)
 def run(self,source_site):
    self.preflight(source_site)
    with (self.output/'RESTORE_STARTED').open('x') as f:f.write('Inspect partial state on failure; never auto-retry.\n')
    env=read_env(self.output/'.env');source=self.encryption_source()
    keys=set(LOCAL_KEYS) if self.components is None else set().union(*(COMPONENT_KEYS.get(c,set()) for c in self.components))
    env.update({k:source[k] for k in keys if source.get(k)})
    # Preserve local database passwords required by restored service configuration.
    if self.components is None:
        env.update({k:source[k] for k in env if k.endswith(('_DB_PASSWORD','_DB_ROOT_PASSWORD')) and source.get(k)})
    write_env(self.output/'.env',env)
    # Raw Rallly clusters must retain their PostgreSQL major and encryption/storage keys.
    rallly_archive=self.backup/'volumes/rallly-selfhosted_db-data.tgz'
    if self.selected(rallly_archive.name) and rallly_archive.exists():
        with tarfile.open(rallly_archive) as archive:
            # PostgreSQL 18 official images store clusters under 18/docker/.
            # Ignore per-database PG_VERSION files in base/*.
            candidates=[m for m in archive if m.isfile() and (
                m.name.lstrip('./')=='PG_VERSION' or
                re.fullmatch(r'([0-9]+)/docker/PG_VERSION',m.name.lstrip('./')))]
            if len(candidates)!=1:raise ValueError('Cannot determine unique Rallly cluster version')
            major=archive.extractfile(candidates[0]).read().decode().strip()
            prefix=candidates[0].name.lstrip('./').split('/')[0]
            if '/' in candidates[0].name.lstrip('./') and prefix!=major:
                raise ValueError('Rallly cluster directory/version mismatch')
        if not major.isdigit():raise ValueError('Invalid PostgreSQL major')
        r_env=read_env(self.output/'rallly/.env')
        with tarfile.open(self.backup/'bind_mounts/rallly-selfhosted-env.tgz') as archive:
            members=[m for m in archive if m.isfile() and m.name.removeprefix('./')=='.env']
            if len(members)!=1:raise ValueError('Expected exactly one Rallly .env archive member')
            text=archive.extractfile(members[0]).read().decode()
        temp=self.output/'rallly/source.env';temp.write_text(text);temp.chmod(0o600)
        old=read_env(temp)
        r_env.update({k:old[k] for k in ('SECRET_PASSWORD','POSTGRES_PASSWORD','S3_ACCESS_KEY_ID','S3_SECRET_ACCESS_KEY','GARAGE_RPC_SECRET')})
        r_env.update(POSTGRES_VERSION=major,POSTGRES_DATA_MOUNT='/var/lib/postgresql' if int(major)>=18 else '/var/lib/postgresql/data')
        write_env(self.output/'rallly/.env',r_env);temp.unlink()
    restored=[];verified={}
    for project,service,destination,archive in VOLUMES:
        if self.selected(archive) and (self.backup/'volumes'/archive).is_file():
            self.volume(project,service,destination,archive);restored.append(archive)
    for service,prefix in PG:
        file=service+'.sql.gz'
        if not self.selected(file) or not (self.backup/'db'/file).is_file():continue
        self.dc('core','up','-d',service);self.ready('core',service)
        self.sql('core',file,['exec','-T',service,'psql','-v','ON_ERROR_STOP=1','-U',env[prefix+'_DB_USER'],'-d',env[prefix+'_DB_NAME']])
        expected=copy_counts(self.backup/'db'/file)
        for table,count in expected.items():
            actual=self.dc('core','exec','-T',service,'psql','-v','ON_ERROR_STOP=1','-U',env[prefix+'_DB_USER'],'-d',env[prefix+'_DB_NAME'],'-Atc',f'SELECT count(*) FROM public."{table}"',capture_output=True,text=True).stdout.strip()
            if int(actual)!=count:raise ValueError('Restored PostgreSQL COPY count mismatch')
        verified[file]=len(expected);restored.append(file)
    for project,service,file,password,database in [
      ('rootedpsyche','rootedpsyche-wordpress-db','rootedpsyche-wordpress-all-databases.sql.gz','ROOTEDPSYCHE_WP_DB_ROOT_PASSWORD','wordpress'),
      ('dank','dank-wordpress-db','dank-wordpress-all-databases.sql.gz','DANK_WP_DB_ROOT_PASSWORD','dank_wordpress')]:
        if not self.selected(file) or not (self.backup/'db'/file).is_file():continue
        self.dc(project,'up','-d',service);self.ready(project,service)
        self.sql(project,file,['exec','-T','-e','MYSQL_PWD='+env[password],service,'mariadb','-uroot','--one-database',database]);restored.append(file)
    # ERPNext system users are never restored. Preserve only the site's encryption key/DB identity.
    erp=self.backup/'db/erpnext-all-databases.sql.gz'
    if self.selected(erp.name) and erp.exists():
        if not source_site or not re.fullmatch(r'[a-zA-Z0-9.-]+',source_site):raise ValueError('--source-site required')
        script="import json,pathlib,sys;p=pathlib.Path('sites')/sys.argv[1]/'site_config.json';print(json.dumps(json.loads(p.read_text())))"
        cfg=json.loads(self.dc('core','run','--rm','--no-deps','--entrypoint','python','erpnext-backend','-c',script,source_site,capture_output=True,text=True).stdout)
        db=cfg['db_name'];password=cfg['db_password']
        if not re.fullmatch(r'[A-Za-z0-9_]+',db):raise ValueError('Unexpected ERP database identity')
        self.dc('core','up','-d','erpnext-db');self.ready('core','erpnext-db')
        sql="SET sql_mode='NO_BACKSLASH_ESCAPES'; CREATE DATABASE `"+db+"`; CREATE USER '"+db+"'@'%' IDENTIFIED BY '"+password.replace("'","''")+"'; GRANT ALL ON `"+db+"`.* TO '"+db+"'@'%';"
        self.dc('core','exec','-T','-e','MYSQL_PWD='+env['ERPNEXT_DB_ROOT_PASSWORD'],'erpnext-db','mariadb','-uroot',input=sql.encode())
        self.sql('core',erp.name,['exec','-T','-e','MYSQL_PWD='+env['ERPNEXT_DB_ROOT_PASSWORD'],'erpnext-db','mariadb','-uroot','--one-database',db])
        target_site=env['ERPNEXT_SITE_NAME']
        if not re.fullmatch(r'[a-zA-Z0-9.-]+',target_site):raise ValueError('Invalid test ERP hostname')
        if target_site==source_site:raise ValueError('Source ERP hostname must differ from test hostname')
        script="import json,pathlib,sys;s=pathlib.Path('sites');p=s/sys.argv[1];q=s/sys.argv[2];p.rename(q) if p!=q else None;f=q/'site_config.json';c=json.loads(f.read_text());c.update(db_host='erpnext-db',db_user=c['db_name'],host_name='https://'+sys.argv[2],maintenance_mode=1,pause_scheduler=1);f.write_text(json.dumps(c));f.chmod(0o600)"
        self.dc('core','run','--rm','--no-deps','--entrypoint','python','erpnext-backend','-c',script,source_site,target_site)
        restored.append(erp.name)
    # Preserve all bind archives privately, never activate backed-up production NGINX.
    quarantine=self.output/'restored-bind-mounts';quarantine.mkdir(mode=0o700)
    for path in self.bind_archives():
        destination=quarantine/path.stem;destination.mkdir(mode=0o700)
        subprocess.run(['tar','-xzf',str(path),'-C',str(destination)],check=True)
        restored.append(path.name)
        if path.name=='documenso-certs.tgz':
            cert=destination/'certs/cert.p12'
            if not cert.is_file():raise ValueError('Missing Documenso signing certificate')
            shutil.copyfile(cert,self.output/'certs/cert.p12');(self.output/'certs/cert.p12').chmod(0o644)
        if path.name=='listmonk.tgz':
            uploads=destination/'listmonk/uploads'
            if uploads.is_dir():
                config=yaml.safe_load((self.output/'core.yml').read_text())
                config['services']['listmonk']['volumes']=[str(uploads)+':/listmonk/uploads:rw']
                (self.output/'core.yml').write_text(yaml.safe_dump(config,sort_keys=False))
    report={'restored':restored,'selected_components':sorted(self.components) if self.components is not None else 'full-stack',
      'removed_secret_metadata':self.removed_secret_metadata,
      'scope':'Selected components only; not full-stack recovery acceptance' if self.components is not None else 'Full archive recovery',
      'postgres_copy_tables_verified':verified,'apps_started':False,'external_egress':False,'migrations_run':False,
      'acceptance':'Pending endpoint remapping, health/data checks and operator review. Do not start schedulers.'}
    (self.output/'restore-receipt.json').write_text(json.dumps(report,indent=2))
    print('Archive recovery completed into isolated projects. Applications remain stopped for endpoint and version review.')


if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('environment',type=Path);p.add_argument('backup',type=Path);p.add_argument('--source-site')
 p.add_argument('--components',nargs='+',choices=COMMERCE_COMPONENTS,help='Restore only these commerce components; omit for full recovery')
 p.add_argument('--check-only',action='store_true',help='Validate the complete snapshot and restore prerequisites without mutation')
 p.add_argument('--key-file',type=Path,help='Private file containing exactly the selected original Appsmith/n8n encryption keys')
 p.add_argument('--allow-removed-secret-metadata',action='store_true',help='Acknowledge removed meta/.env/Rallly env archive only; all other hashes remain mandatory')
 a=p.parse_args();recovery=Recovery(a.environment,a.backup,a.components,a.key_file,a.allow_removed_secret_metadata)
 if a.check_only:recovery.preflight(a.source_site);print('Restore prerequisites validated; no volumes or databases created.')
 else:recovery.run(a.source_site)
