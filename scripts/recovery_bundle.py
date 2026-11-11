#!/usr/bin/env python3
"""Versioned, private nightly-backup inventory and exact-image recovery.

Container inspection is captured in memory only. Never serialize Config.Env,
labels, credentials or raw inspect output into reports.
"""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import tarfile


IMAGE_ARCHIVE = 'images/runtime-images.tar.gz'
MANIFEST = 'meta/recovery-bundle.json'
CORE = ('signaturegate-postgres', 'mushroomprocess-bridge-postgres',
        'nocodb-meta-postgres', 'listmonk-postgres', 'documenso-postgres',
        'erpnext-db', 'erpnext-redis-cache', 'erpnext-redis-queue', 'nocodb',
        'listmonk', 'n8n', 'appsmith', 'documenso', 'erpnext-backend',
        'erpnext-websocket', 'erpnext-queue-short', 'erpnext-queue-long',
        'erpnext-scheduler', 'erpnext-frontend')
GROUPS = {
    'core': [('core', s, s) for s in CORE],
    'rootedpsyche': [('rootedpsyche', s, None) for s in
                     ('rootedpsyche-wordpress-db', 'rootedpsyche-wordpress')],
    'dank': [('dank', s, None) for s in ('dank-wordpress-db', 'dank-wordpress')],
    'librechat': [('core', s, s) for s in ('librechat-mongodb', 'librechat')],
    'librechat-kids': [('core', s, s) for s in ('librechat-kids-mongodb', 'librechat-kids')],
    'scheduling': [('tymeslot', 'tymeslot', 'rootedops-tymeslot'),
                   ('rallly', 'web', 'rallly-selfhosted-web-1'),
                   ('rallly', 'db', 'rallly-selfhosted-db-1'),
                   ('rallly', 'garage', 'rallly-selfhosted-garage-1')],
}
# Stable archive names shared with the full restorer. SQL databases have logical
# dumps; their raw live data volumes are deliberately excluded.
VOLUME_SPECS = [
    ('core', 'nocodb', '/usr/app/data', 'nocodb_data.tgz'),
    ('core', 'n8n', '/home/node/.n8n', 'n8n_data.tgz'),
    ('core', 'appsmith', '/appsmith-stacks', 'appsmith_stacks.tgz'),
    *[('core', 'erpnext-backend', '/home/frappe/frappe-bench/' + k,
       'erpnext_' + k + '.tgz') for k in ('sites', 'apps', 'logs')],
    ('core', 'erpnext-redis-cache', '/data', 'erpnext_redis_cache_data.tgz'),
    ('core', 'erpnext-redis-queue', '/data', 'erpnext_redis_queue_data.tgz'),
    ('rootedpsyche', 'rootedpsyche-wordpress', '/var/www/html', 'rootedpsyche-wordpress-html.tgz'),
    ('dank', 'dank-wordpress', '/var/www/html', 'dank-wordpress-html.tgz'),
    ('tymeslot', 'tymeslot', '/app/data', 'rootedops-scheduling_tymeslot_data.tgz'),
    ('tymeslot', 'tymeslot', '/var/lib/postgresql/data', 'rootedops-scheduling_tymeslot_pg.tgz'),
    ('rallly', 'db', None, 'rallly-selfhosted_db-data.tgz'),
    ('rallly', 'garage', '/var/lib/garage/meta', 'rallly-selfhosted_garage-meta.tgz'),
    ('rallly', 'garage', '/var/lib/garage/data', 'rallly-selfhosted_garage-data.tgz'),
]
for suffix in ('', '-kids'):
    name = 'librechat' + suffix
    VOLUME_SPECS.extend([
        ('core', name + '-mongodb', '/data/db', name + '-mongodb.tgz'),
        ('core', name + '-mongodb', '/data/configdb', name + '-mongodb-config.tgz'),
        *[('core', name, dest, name + '-' + kind + '.tgz') for dest, kind in
          (('/app/data', 'data'), ('/app/uploads', 'uploads'), ('/app/api/logs', 'logs'))],
    ])
PG = [('signaturegate-postgres', 'SIG'), ('mushroomprocess-bridge-postgres', 'MP_BRIDGE'),
      ('listmonk-postgres', 'LISTMONK'), ('nocodb-meta-postgres', 'NC'), ('documenso-postgres', 'DOCUMENSO')]
LIVE_DATABASES = {s for s, _ in PG} | {'erpnext-db', 'rootedpsyche-wordpress-db', 'dank-wordpress-db'}
DISPOSABLE_MOUNTS = {('documenso', '/home/nodejs/.cache/ms-playwright')}
HEX_ID = re.compile(r'sha256:[0-9a-f]{64}')


def private_json(path, value):
    temporary = path.with_suffix('.new')
    with temporary.open('x') as stream:
        os.chmod(temporary, 0o600)
        json.dump(value, stream, indent=2)
        stream.write('\n')
    temporary.replace(path)


def checked_output(command):
    # Exceptions must not echo raw inspect responses or commands containing paths.
    try:
        return subprocess.check_output(command, text=True, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError:
        raise RuntimeError('Docker recovery inventory command failed; inspect private diagnostics') from None


def make_inventory(containers, volume_names):
    records, groups = [], {}
    for group, specs in GROUPS.items():
        found = []
        for project, service, fixed_name in specs:
            matches = [c for c in containers if
                       (c['Name'].lstrip('/') == fixed_name if fixed_name else
                        (c.get('Config', {}).get('Labels') or {}).get('com.docker.compose.service') == service)]
            if len(matches) > 1:
                raise ValueError('Ambiguous source service: ' + service)
            if matches:
                found.append((project, service, matches[0]))
        if not found:
            # Full nightly coverage is explicit. An optional application can be
            # absent only if neither its containers nor its persistent volumes exist.
            prefixes = {'dank': ('dank_wordpress',), 'librechat': ('librechat_',),
                        'librechat-kids': ('librechat_kids_',),
                        'scheduling': ('tymeslot_', 'rallly-selfhosted_')}.get(group, ())
            orphaned = any(any(p in v for p in prefixes) and not (group == 'librechat' and 'librechat_kids_' in v) for v in volume_names)
            if group in ('core', 'rootedpsyche') or orphaned:
                raise ValueError('Missing source containers for installed group: ' + group)
            groups[group] = 'not-installed'
            continue
        if len(found) != len(specs):
            raise ValueError('Partially installed source group: ' + group)
        groups[group] = 'installed'
        for project, service, container in found:
            image = container.get('Image', '')
            if not HEX_ID.fullmatch(image):
                raise ValueError('Missing immutable source image for ' + service)
            records.append({'project': project, 'service': service,
                            'container': container['Name'].lstrip('/'), 'image_id': image,
                            'container_id': container.get('Id'),
                            'running': bool(container.get('State', {}).get('Running'))})
    by_key = {(r['project'], r['service']): r for r in records}
    source_by_name = {c['Name'].lstrip('/'): c for c in containers}
    volumes, binds = [], []
    covered = set()
    for project, service, target, archive in VOLUME_SPECS:
        record = by_key.get((project, service))
        if not record:
            continue
        source = source_by_name[record['container']]
        matches = [m for m in source.get('Mounts', []) if
                   (m['Destination'] == target if target else m['Destination'].startswith('/var/lib/postgresql'))]
        if len(matches) != 1 or matches[0]['Type'] != 'volume' or not matches[0].get('Name'):
            raise ValueError('Missing/ambiguous persistent volume for ' + service + ': ' + str(target))
        mount = matches[0]
        volumes.append({'project': project, 'service': service, 'container': record['container'],
                        'destination': mount['Destination'], 'volume': mount['Name'],
                        'archive': 'volumes/' + archive})
        covered.add((record['container'], mount['Destination']))
    backed_volume_names = {r['volume'] for r in volumes}
    for record in records:
        service = record['service']
        for mount in source_by_name[record['container']].get('Mounts', []):
            dest = mount['Destination']
            if (record['container'], dest) in covered or (service, dest) in DISPOSABLE_MOUNTS:
                continue
            # ERP workers/frontend share the exact apps/sites/log volumes already
            # archived through the backend. One copy covers every consumer.
            if mount['Type'] == 'volume' and mount.get('Name') in backed_volume_names:
                continue
            if service in LIVE_DATABASES and mount['Type'] == 'volume':
                continue  # Logical SQL captures this database; never archive live raw clusters.
            if mount['Type'] != 'bind':
                raise ValueError('Unmapped persistent mount for ' + service + ': ' + dest)
            source = mount['Source']
            if any(c in source + dest for c in '\t\r\n,') or not source.startswith('/'):
                raise ValueError('Unsupported bind path')
            binds.append({'project': record['project'], 'service': service, 'source': source,
                          'destination': dest, 'read_only': not mount.get('RW', False),
                          'archive': 'bind_mounts/runtime-bind-%03d.tgz' % len(binds)})
    payloads = ['meta/.env', 'meta/docker-compose.yml', 'meta/frappe-app-versions.txt', IMAGE_ARCHIVE]
    payloads += ['db/' + s + '.sql.gz' for s, _ in PG]
    payloads += ['db/erpnext-all-databases.sql.gz', 'db/rootedpsyche-wordpress-all-databases.sql.gz']
    if groups['dank'] == 'installed':
        payloads.append('db/dank-wordpress-all-databases.sql.gz')
    if groups['scheduling'] == 'installed':
        payloads += ['bind_mounts/rallly-selfhosted-env.tgz', 'meta/tymeslot.compose.yml']
    payloads += [r['archive'] for r in volumes + binds]
    return {'format_version': 2, 'groups': groups, 'services': records,
            'volumes': volumes, 'binds': binds, 'required_payloads': sorted(payloads),
            'image_archive': IMAGE_ARCHIVE,
            'excluded': {'minecraft': 'legacy bind snapshot only; not started during full test recovery',
                         'documenso_playwright_cache': 'rebuildable browser cache; not application data'}}


def capture(backup, docker):
    ids = checked_output(docker + ['ps', '-aq']).split()
    containers = json.loads(checked_output(docker + ['inspect', *ids])) if ids else []
    names = checked_output(docker + ['volume', 'ls', '-q']).splitlines()
    inventory = make_inventory(containers, names)
    private_json(backup / MANIFEST, inventory)
    return inventory


def verify_sources(backup, docker, allow_stopped=False):
    original = json.loads((backup / MANIFEST).read_text())
    ids = checked_output(docker + ['ps', '-aq']).split()
    current = make_inventory(json.loads(checked_output(docker + ['inspect', *ids])) if ids else [],
                             checked_output(docker + ['volume', 'ls', '-q']).splitlines())
    if allow_stopped:
        for inventory in (current, original):
            for record in inventory['services']:
                record.pop('running', None)
    if current != original:
        raise ValueError('Source containers, images, mounts or installation changed during backup; refusing mixed snapshot')


def validate_bundle(backup):
    path = backup / MANIFEST
    if not path.is_file():
        raise ValueError('Full recovery requires a fresh format-2 nightly backup with runtime images and service inventory')
    manifest = json.loads(path.read_text())
    if manifest.get('format_version') != 2 or manifest.get('image_archive') != IMAGE_ARCHIVE:
        raise ValueError('Unsupported recovery bundle format')
    expected_groups = set(GROUPS)
    if set(manifest['groups']) != expected_groups or any(
            v not in ('installed', 'not-installed') for v in manifest['groups'].values()):
        raise ValueError('Invalid installed-group inventory')
    if any(manifest['groups'][g] != 'installed' for g in ('core', 'rootedpsyche')):
        raise ValueError('Full recovery is missing required base groups')
    expected_services = {(p, s) for g, specs in GROUPS.items() if manifest['groups'][g] == 'installed'
                         for p, s, _ in specs}
    actual_services = [(r['project'], r['service']) for r in manifest['services']]
    if len(actual_services) != len(set(actual_services)) or set(actual_services) != expected_services:
        raise ValueError('Incomplete/duplicate service inventory')
    if any(not HEX_ID.fullmatch(r['image_id']) for r in manifest['services']):
        raise ValueError('Invalid source image identity')
    required = set(manifest['required_payloads'])
    expected_volumes = {('volumes/' + a, p, s) for p, s, _, a in VOLUME_SPECS if (p, s) in expected_services}
    actual_volumes = {(r['archive'], r['project'], r['service']) for r in manifest['volumes']}
    if expected_volumes != actual_volumes or len(actual_volumes) != len(manifest['volumes']):
        raise ValueError('Incomplete/duplicate volume inventory')
    needed = {a for a, _, _ in expected_volumes} | {'meta/.env', IMAGE_ARCHIVE,
              'meta/docker-compose.yml', 'meta/frappe-app-versions.txt', 'db/erpnext-all-databases.sql.gz',
              'db/rootedpsyche-wordpress-all-databases.sql.gz'} | {'db/' + s + '.sql.gz' for s, _ in PG}
    if manifest['groups']['dank'] == 'installed':
        needed.add('db/dank-wordpress-all-databases.sql.gz')
    if manifest['groups']['scheduling'] == 'installed':
        needed |= {'bind_mounts/rallly-selfhosted-env.tgz', 'meta/tymeslot.compose.yml'}
    for index, record in enumerate(manifest['binds']):
        if record['archive'] != 'bind_mounts/runtime-bind-%03d.tgz' % index:
            raise ValueError('Invalid runtime bind archive identity')
        if (record['project'], record['service']) not in expected_services:
            raise ValueError('Unknown bind service')
        if not record['destination'].startswith('/') or '..' in Path(record['destination']).parts:
            raise ValueError('Unsafe bind destination')
        needed.add(record['archive'])
    if not needed <= required:
        raise ValueError('Recovery inventory omits required payloads')
    # A checksum list alone cannot prove completeness; the contract must name every
    # expected payload, and each expected file must itself be in the original list.
    sums = set()
    for line in (backup / 'SHA256SUMS').read_text().splitlines():
        match = re.fullmatch(r'[a-fA-F0-9]{64} [ *](.+)', line)
        if not match:
            raise ValueError('Invalid checksum entry')
        name = Path(match[1])
        if name.is_absolute() or '..' in name.parts:
            raise ValueError('Unsafe checksum path')
        normalized = name.as_posix()
        if normalized in sums:
            raise ValueError('Duplicate checksum entry')
        sums.add(normalized)
    if not (required | {MANIFEST}) <= sums:
        raise ValueError('Recovery payload missing from SHA256SUMS')
    actual_files = {str(p.relative_to(backup)) for p in backup.rglob('*')
                    if p.is_file() and p.name != 'SHA256SUMS'}
    if actual_files != sums:
        raise ValueError('Snapshot file inventory differs from SHA256SUMS')
    if {str(p.relative_to(backup)) for p in (backup / 'volumes').glob('*.tgz')} != {a for a, _, _ in expected_volumes}:
        raise ValueError('Volume payloads differ from installed service inventory')
    if {str(p.relative_to(backup)) for p in (backup / 'db').glob('*.gz')} != {n for n in needed if n.startswith('db/')}:
        raise ValueError('Database payloads differ from installed service inventory')
    for name in required:
        p = backup / name
        if Path(name).is_absolute() or '..' in Path(name).parts or not p.is_file() or not p.resolve().is_relative_to(backup.resolve()):
            raise ValueError('Missing or unsafe recovery payload: ' + name)
        if p.stat().st_size == 0:
            raise ValueError('Empty recovery payload: ' + name)
    # Scan to gzip EOF, including CRC, without expanding image layers on disk.
    with gzip.open(backup / IMAGE_ARCHIVE, 'rb') as stream:
        while stream.read(1024 * 1024):
            pass
    with tarfile.open(backup / IMAGE_ARCHIVE, 'r:gz') as archive:
        entries = [m for m in archive if m.name == 'manifest.json' and m.isfile()]
        if len(entries) != 1 or entries[0].size > 10 * 1024 * 1024:
            raise ValueError('Invalid docker image archive manifest')
        if not json.load(archive.extractfile(entries[0])):
            raise ValueError('Empty docker image archive')
    return manifest


def image_tag(image_id):
    return 'rootedops-recovery:' + image_id.split(':', 1)[1]


def config_hashes(output):
    return {name: hashlib.sha256((output / name).read_bytes()).hexdigest()
            for name in ('core.yml', 'rootedpsyche.yml', 'dank.yml', 'tymeslot.yml', 'rallly/compose.yml')}


def prepare_images(output, backup):
    import yaml
    if (output / 'TEST_ENVIRONMENT').read_text().strip() != 'rootedops-full-test':
        raise ValueError('Explicit isolated full-test environment required')
    if (output / 'RESTORE_STARTED').exists() or checked_output(['docker', 'ps', '-aq']).strip():
        raise ValueError('Prepare images only before restoration on an empty test host')
    manifest = validate_bundle(backup)
    subprocess.run(['sha256sum', '--check', '--quiet', 'SHA256SUMS'], cwd=backup, check=True)
    configs = {}
    for project in ('core', 'rootedpsyche', 'dank', 'tymeslot', 'rallly'):
        path = output / ('rallly/compose.yml' if project == 'rallly' else project + '.yml')
        config = yaml.safe_load(path.read_text())
        if config.get('networks', {}).get('default', {}).get('internal') is not True:
            raise ValueError('Outbound isolation required before image preparation')
        configs[project] = (path, config)
    subprocess.run(['docker', 'image', 'load', '--input', str(backup / IMAGE_ARCHIVE)], check=True)
    ids = sorted({r['image_id'] for r in manifest['services']})
    for image in ids:
        actual = checked_output(['docker', 'image', 'inspect', '--format', '{{.Id}}', image]).strip()
        if actual != image:
            raise ValueError('Loaded image does not match backup identity')
        subprocess.run(['docker', 'image', 'tag', image, image_tag(image)], check=True)
    sources = {(r['project'], r['service']): r['image_id'] for r in manifest['services']}
    # Initializers share the actual ERP backend image; never rebuild floating refs.
    for service in ('erpnext-apps-init', 'erpnext-configurator', 'erpnext-bootstrap'):
        sources['core', service] = sources['core', 'erpnext-backend']
    for project, (path, config) in configs.items():
        for service, spec in config['services'].items():
            image = sources.get((project, service))
            if image:
                spec['image'] = image_tag(image)
                spec['pull_policy'] = 'never'
                spec.pop('build', None)
                if service in ('librechat-mongodb', 'librechat-kids-mongodb'):
                    # mongo declares /data/configdb as an anonymous image volume.
                    # Give recovered bytes a durable test-only Compose volume.
                    volume = service.replace('-', '_') + '_config'
                    spec['volumes'] = [m for m in spec.get('volumes', []) if
                                       (m.split(':')[1] if isinstance(m, str) else m['target']) != '/data/configdb']
                    spec['volumes'].append(volume + ':/data/configdb')
                    config.setdefault('volumes', {})[volume] = None
            elif service != 'mailpit':
                # Preserve opt-in tools, but keep absent runtime groups disabled.
                # Tool-profile images aren't started by full_restore.
                if not spec.get('profiles'):
                    spec['profiles'] = ['not-in-backup']
        path.write_text(yaml.safe_dump(config, sort_keys=False))
        path.chmod(0o600)
    receipt = {'backup_inventory_sha256': hashlib.sha256((backup / MANIFEST).read_bytes()).hexdigest(),
               'images': ids, 'config_sha256': config_hashes(output), 'apps_started': False}
    private_json(output / 'backup-image-receipt.json', receipt)
    print('Exact backup images loaded and isolated Compose pinned; no containers started.')


def verify_images(output, backup):
    manifest = validate_bundle(backup)
    path = output / 'backup-image-receipt.json'
    if not path.is_file():
        raise ValueError('Run full_restore.py --prepare-images using this complete backup first')
    receipt = json.loads(path.read_text())
    if receipt['backup_inventory_sha256'] != hashlib.sha256((backup / MANIFEST).read_bytes()).hexdigest() or receipt['config_sha256'] != config_hashes(output):
        raise ValueError('Backup/image preparation receipt no longer matches snapshot or Compose')
    for image in sorted({r['image_id'] for r in manifest['services']}):
        if checked_output(['docker', 'image', 'inspect', '--format', '{{.Id}}', image_tag(image)]).strip() != image:
            raise ValueError('Prepared runtime image identity changed')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('capture', 'records', 'validate', 'verify-sources'))
    parser.add_argument('backup', type=Path)
    parser.add_argument('--docker-command', default='sudo docker')
    parser.add_argument('--kind', choices=('images', 'volumes', 'binds', 'cold', 'dank', 'rootedpsyche', 'groups'))
    parser.add_argument('--allow-stopped', action='store_true')
    args = parser.parse_args()
    if args.action == 'capture':
        capture(args.backup, shlex.split(args.docker_command))
    elif args.action == 'verify-sources':
        verify_sources(args.backup, shlex.split(args.docker_command), args.allow_stopped)
    elif args.action == 'validate':
        validate_bundle(args.backup)
        print('Complete nightly recovery inventory and image archive validated.')
    else:
        m = json.loads((args.backup / MANIFEST).read_text())
        if args.kind == 'images':
            print('\n'.join(sorted({r['image_id'] for r in m['services']})))
        elif args.kind == 'volumes':
            for r in m['volumes']:
                print(r['volume'] + '\t' + Path(r['archive']).name)
        elif args.kind == 'binds':
            for r in m['binds']:
                print(r['source'] + '\t' + Path(r['archive']).name)
        elif args.kind == 'cold':
            # Stop clients before embedded/raw database services; restart in reverse.
            records = [r for r in m['services'] if r['running'] and r['service'] not in LIVE_DATABASES]
            records.sort(key=lambda r: r['service'].endswith('-mongodb') or r['service'] in ('db', 'garage', 'erpnext-redis-cache', 'erpnext-redis-queue'))
            print('\n'.join(r['container'] for r in records))
        elif args.kind in ('dank', 'rootedpsyche'):
            for r in m['services']:
                if r['service'] == ('dank-wordpress-db' if args.kind == 'dank' else 'rootedpsyche-wordpress-db'):
                    print(r['container'])
        elif args.kind == 'groups':
            print(json.dumps(m['groups'], sort_keys=True))


if __name__ == '__main__':
    main()
