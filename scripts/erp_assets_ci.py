#!/usr/bin/env python3
"""Round-trip a real image-declared nested ERP assets volume on disposable CI."""
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import uuid

import yaml
from full_restore import Recovery
from recovery_bundle import (GROUPS, VOLUME_SPECS, ERP_ASSETS_TARGET,
                             make_inventory, asset_volume_records, configure_asset_volumes)


def main():
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise SystemExit('Run only on a disposable GitHub Actions runner')
    project = 'erp-assets-ci-' + uuid.uuid4().hex[:8]
    source_name, source_parent = project + '-source', project + '-source-sites'
    source_child, recovery = None, None
    subprocess.run(['docker', 'build', '--network=none', '-t', project + ':fixture', '-'],
                   input=('FROM alpine:3.20\nVOLUME ["' + ERP_ASSETS_TARGET + '"]\n').encode(), check=True)
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        backup, output = root / 'backup', root / 'test'
        (backup / 'volumes').mkdir(parents=True)
        output.mkdir(); (output / '.env').touch()
        try:
            # Named parent + image-declared anonymous child reproduces the
            # production failure. Write distinct bytes across the mount boundary.
            subprocess.run(['docker', 'run', '--name', source_name, '--network', 'none',
                            '-v', source_parent + ':/home/frappe/frappe-bench/sites', project + ':fixture',
                            'sh', '-ec', 'printf parent-state > /home/frappe/frappe-bench/sites/site.txt; '
                            'printf child-assets > ' + ERP_ASSETS_TARGET + '/assets.txt; '
                            'ln -s ../../apps/frappe/frappe/public ' + ERP_ASSETS_TARGET + '/frappe'], check=True)
            actual = json.loads(subprocess.check_output(['docker', 'inspect', source_name], text=True))[0]
            child_mount = next(m for m in actual['Mounts'] if m['Destination'] == ERP_ASSETS_TARGET)
            source_child = child_mount['Name']
            source = []
            for group in ('core', 'rootedpsyche'):
                for p, service, name in GROUPS[group]:
                    mounts = [{'Destination': target, 'Type': 'volume', 'Name': archive[:-4]}
                              for p2, s, target, archive in VOLUME_SPECS if (p2, s) == (p, service)]
                    if service == 'erpnext-backend':
                        targets = {m['Destination'] for m in actual['Mounts']}
                        mounts = [m for m in mounts if m['Destination'] not in targets] + actual['Mounts']
                    if service == 'erpnext-frontend':
                        mounts.append(dict(child_mount, RW=False))
                    source.append({'Name': '/' + (name or 'fixture-' + service), 'Image': actual['Image'],
                                   'Config': {'Labels': {'com.docker.compose.service': service}},
                                   'State': {'Running': False}, 'Mounts': mounts})
            inventory = make_inventory(source, [])
            assets = asset_volume_records(inventory)
            assert len(assets) == 1 and assets[0]['consumers'] == ['erpnext-backend', 'erpnext-frontend']
            selected = [r for r in inventory['volumes'] if r['archive'] == 'volumes/erpnext_sites.tgz'] + assets
            for record in selected:
                data = subprocess.check_output(['docker', 'run', '--rm', '--network', 'none',
                                                '-v', record['volume'] + ':/volume:ro', 'alpine:3.20',
                                                'tar', '-czf', '-', '-C', '/volume', '.'])
                path = backup / record['archive']; path.write_bytes(data)
                subprocess.run(['bash', '-c', 'source "$1"; validate_managed_volume_archive "$2"',
                                'validate', str(Path(__file__).resolve().parents[1] / 'backup/volume-tools.sh'), str(path)], check=True)
            with tarfile.open(backup / 'volumes/erpnext_sites.tgz') as archive:
                assert not any(m.name.endswith('assets/assets.txt') for m in archive)
            subprocess.run(['docker', 'rm', source_name], check=True)
            subprocess.run(['docker', 'volume', 'rm', source_parent, source_child], check=True)
            config = {'name': project, 'services': {
                service: {'image': project + ':fixture', 'volumes': ['sites:/home/frappe/frappe-bench/sites']}
                for service in ('erpnext-backend', 'erpnext-frontend')},
                'volumes': {'sites': None}, 'networks': {'default': {'internal': True}}}
            configure_asset_volumes(config, inventory)
            (output / 'core.yml').write_text(yaml.safe_dump(config))
            recovery = Recovery(output, backup)
            for record in selected:
                recovery.volume(record['project'], record['service'], record['destination'], Path(record['archive']).name)
            recovery.dc('core', 'up', '--no-start', '--no-deps', 'erpnext-frontend')
            ids = recovery.dc('core', 'ps', '-aq', capture_output=True, text=True).stdout.split()
            targets = json.loads(subprocess.check_output(['docker', 'inspect', *ids], text=True))
            assert len(targets) == 2 and all(c['State']['Status'] == 'created' for c in targets)
            child_names = {m['Name'] for c in targets for m in c['Mounts'] if m['Destination'] == ERP_ASSETS_TARGET}
            assert len(child_names) == 1
            parent_names = {m['Name'] for c in targets for m in c['Mounts'] if m['Destination'].endswith('/sites')}
            assert len(parent_names) == 1 and not child_names & parent_names
            assert next(m for c in targets if c['Name'].endswith('-erpnext-frontend-1')
                        for m in c['Mounts'] if m['Destination'] == ERP_ASSETS_TARGET)['RW'] is False
            for volume, filename, expected in [(next(iter(parent_names)), 'site.txt', b'parent-state'),
                                               (next(iter(child_names)), 'assets.txt', b'child-assets')]:
                assert subprocess.check_output(['docker', 'run', '--rm', '--network', 'none',
                                                '-v', volume + ':/volume:ro', 'alpine:3.20', 'cat', '/volume/' + filename]) == expected
        finally:
            if recovery:
                recovery.dc('core', 'down', '--volumes')
            subprocess.run(['docker', 'rm', '-f', source_name], capture_output=True)
            for volume in (source_parent, source_child):
                if volume:
                    subprocess.run(['docker', 'volume', 'rm', volume], capture_output=True)
    print('Nested ERP assets round trip passed: distinct parent/child bytes, one shared child archive, read-only frontend, no restored app startup.')


if __name__ == '__main__':
    main()
