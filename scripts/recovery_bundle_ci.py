#!/usr/bin/env python3
"""Native exact-image save/load regression on a disposable CI Docker daemon."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

import yaml
from recovery_bundle import (GROUPS, IMAGE_ARCHIVE, MANIFEST, VOLUME_SPECS,
                             make_inventory, prepare_images, verify_images)


def main():
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise SystemExit('Run only on a disposable GitHub Actions runner')
    subprocess.run(['docker', 'pull', 'alpine:3.20'], check=True)
    image = subprocess.check_output(['docker', 'image', 'inspect', '--format', '{{.Id}}', 'alpine:3.20'], text=True).strip()
    source = []
    for group in ('core', 'rootedpsyche'):
        for project, service, name in GROUPS[group]:
            mounts = [{'Destination': target, 'Type': 'volume', 'Name': archive[:-4]}
                      for p, s, target, archive in VOLUME_SPECS if (p, s) == (project, service)]
            source.append({'Name': '/' + (name or 'fixture-' + service), 'Image': image,
                           'Config': {'Labels': {'com.docker.compose.service': service}},
                           'State': {'Running': False}, 'Mounts': mounts})
    manifest = make_inventory(source, [])
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        backup = root / 'backup'
        for name in manifest['required_payloads']:
            path = backup / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'synthetic payload, not production data')
        (backup / MANIFEST).write_text(json.dumps(manifest))
        with gzip.open(backup / IMAGE_ARCHIVE, 'wb') as stream:
            saved = subprocess.Popen(['docker', 'image', 'save', image], stdout=subprocess.PIPE)
            try:
                while data := saved.stdout.read(1024 * 1024):
                    stream.write(data)
                if saved.wait():
                    raise RuntimeError('Native image save failed')
            finally:
                if saved.poll() is None:
                    saved.kill()
                    saved.wait()
                saved.stdout.close()
        (backup / 'SHA256SUMS').write_text(''.join(
            hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + str(p.relative_to(backup)) + '\n'
            for p in sorted(backup.rglob('*')) if p.is_file() and p.name != 'SHA256SUMS'))
        output = root / 'test'
        output.mkdir()
        (output / 'TEST_ENVIRONMENT').write_text('rootedops-full-test')
        for project in ('core', 'rootedpsyche', 'dank', 'tymeslot', 'rallly'):
            path = output / ('rallly/compose.yml' if project == 'rallly' else project + '.yml')
            path.parent.mkdir(exist_ok=True)
            services = {r['service']: {'image': 'incorrect-floating:latest', 'build': {'context': '.'}}
                        for r in manifest['services'] if r['project'] == project}
            if project == 'core':
                for name in ('erpnext-apps-init', 'erpnext-configurator', 'erpnext-bootstrap'):
                    services[name] = {'build': {'context': '.'}}
            path.write_text(yaml.safe_dump({'name': 'fixture-' + project, 'services': services,
                                           'networks': {'default': {'internal': True}}}))
        prepare_images(output, backup)
        verify_images(output, backup)
        assert not subprocess.check_output(['docker', 'ps', '-aq'], text=True).strip()
        for project in ('core', 'rootedpsyche'):
            config = yaml.safe_load((output / (project + '.yml')).read_text())
            assert all(s['pull_policy'] == 'never' and 'build' not in s for s in config['services'].values())
    print('Native Docker image save/gzip/load preserves exact IDs and starts no containers.')


if __name__ == '__main__':
    main()
