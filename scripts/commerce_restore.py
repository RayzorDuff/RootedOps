#!/usr/bin/env python3
"""Restore selected backups into a freshly rendered commerce-test project only.

Never reads meta/.env into the host environment, starts restored applications,
replaces app code, or restores MariaDB system users. See the recovery runbook.
"""
import argparse
import gzip
import json
from pathlib import Path
import re
import shlex
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = {'mushroomprocess', 'n8n', 'appsmith', 'erpnext'}


def read_env(path):
    values = {}
    for line in path.read_text().splitlines():
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        parsed = shlex.split(value, comments=True)
        values[key] = parsed[0] if parsed else ''
    return values


def copy_counts(path):
    """Count standard public-schema pg_dump COPY rows without retaining data."""
    counts = {}
    table = None
    with gzip.open(path, 'rt', encoding='utf-8') as stream:
        for line in stream:
            if table is not None:
                if line.rstrip('\n') == r'\.':
                    table = None
                else:
                    counts[table] += 1
            else:
                match = re.fullmatch(r'COPY public\.([a-z_][a-z_0-9]*) \(.*\) FROM stdin;\n?', line)
                if match:
                    table = match[1]
                    if table in counts:
                        raise ValueError('Duplicate COPY table')
                    counts[table] = 0
    if table is not None:
        raise ValueError('Unterminated COPY data')
    return counts


def preflight(environment, backup, components, source_site):
    if not components or not set(components) <= COMPONENTS:
        raise ValueError('Select known components explicitly')
    if (environment/'TEST_ENVIRONMENT').read_text().strip() != 'commerce-test':
        raise ValueError('Missing fresh test environment marker')
    env = read_env(environment/'.env')
    if env.get('ERPNEXT_SITE_NAME') != 'erp-test.danks.store' or env.get('MP_BRIDGE_DB_NAME') != 'mushroomprocess_test':
        raise ValueError('Unexpected destination identity')
    import yaml
    config = yaml.safe_load((environment/'compose.yml').read_text())
    if config.get('name') != 'commerce-test':
        raise ValueError('Unexpected Compose project')
    if config.get('networks', {}).get('default', {}).get('internal') is not True:
        raise ValueError('Restored services must use an internal network without external egress')
    if any(options for options in config.get('volumes', {}).values()):
        raise ValueError('External or custom-named restore volumes are forbidden')
    for service in config['services'].values():
        if service.get('container_name') or any(not str(p).startswith('127.0.0.1:') for p in service.get('ports', [])):
            raise ValueError('Destination must use isolated containers and loopback ports')
    required = []
    for component in components:
        if component == 'mushroomprocess':
            required.append(backup/'db/mushroomprocess-bridge-postgres.sql.gz')
        elif component == 'erpnext':
            if not source_site or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]*', source_site):
                raise ValueError('ERP restore requires --source-site from the backup')
            required.extend([backup/'db/erpnext-all-databases.sql.gz', backup/'volumes/erpnext_sites.tgz'])
        else:
            required.append(backup/('volumes/'+component+'_'+('data.tgz' if component == 'n8n' else 'stacks.tgz')))
    if 'n8n' in components:
        if not (backup/'meta/.env').is_file() or not read_env(backup/'meta/.env').get('N8N_ENCRYPTION_KEY'):
            raise ValueError('n8n restore requires the original encryption key in backup/meta/.env')
    for path in required:
        if not path.is_file():
            raise ValueError(f'Missing required backup: {path.name}')
        if path.suffix == '.tgz':
            subprocess.run(['bash', '-c', 'source "$1"; validate_volume_archive "$2"',
                            'preflight', str(ROOT/'backup/volume-tools.sh'), str(path)], check=True)
        else:
            # Verify gzip CRC before any mutation, streaming without retaining PII.
            with gzip.open(path, 'rb') as stream:
                while stream.read(1024*1024):
                    pass
    if 'mushroomprocess' in components:
        copy_counts(backup/'db/mushroomprocess-bridge-postgres.sql.gz')
    if (backup/'SHA256SUMS').is_file():
        subprocess.run(['sha256sum', '--check', '--quiet', 'SHA256SUMS'], cwd=backup, check=True)
    return env


class Restore:
    def __init__(self, environment, backup, env):
        self.environment, self.backup, self.env = environment, backup, env
        self.compose = ['docker', 'compose', '--project-name', 'commerce-test', '--env-file',
                        str(environment/'.env'), '-f', str(environment/'compose.yml')]

    def dc(self, *args, **kwargs):
        return subprocess.run(self.compose + list(args), check=True, **kwargs)

    def ready(self, service):
        for _ in range(120):
            result = self.dc('ps', '-q', service, capture_output=True, text=True)
            cid = result.stdout.strip()
            if cid:
                state = subprocess.run(['docker', 'inspect', '--format', '{{.State.Health.Status}}', cid],
                                       capture_output=True, text=True, check=True).stdout.strip()
                if state == 'healthy':
                    return
            time.sleep(2)
        raise RuntimeError(f'Database readiness timed out: {service}')

    def volume(self, service, destination, archive):
        self.dc('up', '--no-start', '--no-deps', service)
        cid = self.dc('ps', '-a', '-q', service, capture_output=True, text=True).stdout.strip()
        mounts = json.loads(subprocess.run(['docker', 'inspect', '--format', '{{json .Mounts}}', cid],
                                         capture_output=True, text=True, check=True).stdout)
        matches = [m for m in mounts if m['Destination'] == destination and m['Type'] == 'volume']
        if len(matches) != 1 or not matches[0]['Name'].startswith('commerce-test_'):
            raise ValueError('Unexpected restore volume')
        # Fresh project only; never remove existing data silently.
        subprocess.run(['docker', 'run', '--rm', '--network', 'none', '-v', matches[0]['Name']+':/target',
                        '-v', str(self.backup/'volumes')+':/backup:ro', 'alpine:3.20',
                        'sh', '-ec', 'test -z "$(ls -A /target)" || { echo "Target volume is not empty" >&2; exit 1; }; tar -xzf "/backup/$1" -C /target',
                        'restore', archive], check=True)

    def sql(self, archive, *args):
        with gzip.open(self.backup/'db'/archive, 'rb') as stream:
            process = subprocess.Popen(self.compose+list(args), stdin=subprocess.PIPE)
            try:
                while block := stream.read(1024*1024):
                    process.stdin.write(block)
                process.stdin.close()
                if process.wait():
                    raise RuntimeError('Database restore failed')
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.wait()

    def run(self, components, source_site):
        # Refuse previously used projects before stopping anything.
        existing = self.dc('ps', '-a', '-q', capture_output=True, text=True).stdout.strip()
        volumes = subprocess.run(['docker', 'volume', 'ls', '-q', '--filter', 'name=^commerce-test_'],
                                 capture_output=True, text=True, check=True).stdout.strip()
        if existing or volumes:
            raise ValueError('Restore requires a fresh project with no existing containers or volumes')
        marker = self.environment/'RESTORE_STARTED'
        with marker.open('x') as stream:
            stream.write('Do not retry automatically; inspect partial restore on failure.\n')
        if 'n8n' in components:
            source_key = read_env(self.backup/'meta/.env')['N8N_ENCRYPTION_KEY']
            env_path = self.environment/'.env'
            text = env_path.read_text()
            text = re.sub(r'^N8N_ENCRYPTION_KEY=.*$', 'N8N_ENCRYPTION_KEY='+shlex.quote(source_key), text, flags=re.M)
            env_path.write_text(text)
            env_path.chmod(0o600)
        if 'mushroomprocess' in components:
            self.dc('up', '-d', 'mushroomprocess-bridge-postgres')
            self.ready('mushroomprocess-bridge-postgres')
            expected = copy_counts(self.backup/'db/mushroomprocess-bridge-postgres.sql.gz')
            self.sql('mushroomprocess-bridge-postgres.sql.gz', 'exec', '-T',
                     'mushroomprocess-bridge-postgres', 'psql', '-v', 'ON_ERROR_STOP=1',
                     '-U', self.env['MP_BRIDGE_DB_USER'], '-d', self.env['MP_BRIDGE_DB_NAME'])
            for table, count in expected.items():
                actual = self.dc('exec', '-T', 'mushroomprocess-bridge-postgres', 'psql', '-v',
                                 'ON_ERROR_STOP=1', '-U', self.env['MP_BRIDGE_DB_USER'], '-d',
                                 self.env['MP_BRIDGE_DB_NAME'], '-Atc',
                                 f'SELECT count(*) FROM public."{table}"', capture_output=True, text=True)
                if int(actual.stdout.strip()) != count:
                    raise ValueError('Restored COPY row count mismatch: '+table)
            print(f'Verified {len(expected)} restored COPY table counts.')
        for service, destination, archive in [
            ('n8n', '/home/node/.n8n', 'n8n_data.tgz'),
            ('appsmith', '/appsmith-stacks', 'appsmith_stacks.tgz')]:
            if service in components:
                self.volume(service, destination, archive)
        if 'erpnext' in components:
            self.volume('erpnext-backend', '/home/frappe/frappe-bench/sites', 'erpnext_sites.tgz')
            # Preserve the source site's encryption key; change only DB connection identity.
            script = '''import json,pathlib,sys
p=pathlib.Path('sites')/sys.argv[1]/'site_config.json'
c=json.loads(p.read_text());print(c['db_name'])
'''
            result = self.dc('run', '--rm', '--no-deps', '--entrypoint', 'python', 'erpnext-backend',
                             '-c', script, source_site, capture_output=True, text=True)
            database = result.stdout.strip()
            if not re.fullmatch(r'[A-Za-z0-9_]+', database):
                raise ValueError('Unexpected source ERP database name')
            self.dc('up', '-d', 'erpnext-db', 'erpnext-redis-cache', 'erpnext-redis-queue')
            self.ready('erpnext-db')
            password = self.env['ERPNEXT_DB_ROOT_PASSWORD']
            # Random generated alphanumeric DB password; SQL identifiers are validated above.
            import secrets
            site_password = secrets.token_hex(24)
            sql = f"CREATE DATABASE `{database}`; CREATE USER '{database}'@'%' IDENTIFIED BY '{site_password}'; GRANT ALL ON `{database}`.* TO '{database}'@'%';"
            self.dc('exec', '-T', '-e', 'MYSQL_PWD='+password, 'erpnext-db', 'mariadb', '-uroot', input=sql.encode())
            self.sql('erpnext-all-databases.sql.gz', 'exec', '-T', '-e', 'MYSQL_PWD='+password,
                     'erpnext-db', 'mariadb', '-uroot', '--one-database', database)
            script = '''import json,pathlib,sys
sites=pathlib.Path('sites');old=sites/sys.argv[1];new=sites/'erp-test.danks.store'
if old!=new: old.rename(new)
p=new/'site_config.json';c=json.loads(p.read_text());c.update(db_host='erpnext-db',db_user=c['db_name'],db_password=sys.argv[2],host_name='https://erp-test.danks.store',maintenance_mode=1,pause_scheduler=1)
p.write_text(json.dumps(c));p.chmod(0o600)
# Production default-site routing must not survive restore.
(sites/'currentsite.txt').write_text('erp-test.danks.store\\n')
'''
            self.dc('run', '--rm', '--no-deps', '--entrypoint', 'python', 'erpnext-backend', '-c', script, source_site, site_password)
            self.dc('run', '--rm', '--no-deps', 'erpnext-apps-init')
            self.dc('run', '--rm', '--no-deps', 'erpnext-configurator')
        (self.environment/'RESTORE_COMPLETE').write_text('Restored components: '+', '.join(components)+'\n')
        print('Restore complete. Applications remain stopped. Review the recovery runbook before starting them.')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('environment', type=Path)
    p.add_argument('backup', type=Path)
    p.add_argument('--components', nargs='+', required=True, choices=sorted(COMPONENTS))
    p.add_argument('--source-site')
    a = p.parse_args()
    environment, backup = a.environment.resolve(), a.backup.resolve()
    env = preflight(environment, backup, a.components, a.source_site)
    Restore(environment, backup, env).run(a.components, a.source_site)


if __name__ == '__main__':
    main()
