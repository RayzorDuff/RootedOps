import copy
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import recovery_bundle as bundle


def containers(groups=None):
    selected = set(groups or bundle.GROUPS)
    result = []
    for group, specs in bundle.GROUPS.items():
        if group not in selected:
            continue
        for project, service, name in specs:
            record = {'Name': '/' + (name or 'arbitrary-project-' + service + '-1'),
                      'Image': 'sha256:' + hashlib.sha256(service.encode()).hexdigest(),
                      'State': {'Running': True},
                      'Config': {'Env': ['PRIVATE_TOKEN=never-serialize-this'],
                                 'Labels': {'com.docker.compose.service': service}}, 'Mounts': []}
            for p, s, target, archive in bundle.VOLUME_SPECS:
                if (p, s) == (project, service):
                    record['Mounts'].append({'Destination': target or '/var/lib/postgresql',
                                             'Type': 'volume', 'Name': 'actual_' + archive[:-4]})
            result.append(record)
    return result


def write_sums(root):
    (root / 'SHA256SUMS').write_text(''.join(
        hashlib.sha256(p.read_bytes()).hexdigest() + '  ./' + str(p.relative_to(root)) + '\n'
        for p in sorted(root.rglob('*')) if p.is_file() and p.name != 'SHA256SUMS'))


def write_fixture(root, manifest=None):
    manifest = manifest or bundle.make_inventory(containers(), [])
    if 'images' not in manifest:
        local = [{'Id': r['image_id'], 'Size': 4096, 'Os': 'linux', 'Architecture': 'amd64', 'RepoDigests': []}
                 for r in manifest['services']]
        bundle.select_images(manifest, local, lambda ref: {})
    for name in manifest['required_payloads']:
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b'synthetic nonempty payload')
    (root / bundle.MANIFEST).write_text(json.dumps(manifest))
    if manifest['image_archive']:
        with tarfile.open(root / bundle.IMAGE_ARCHIVE, 'w:gz') as archive:
            data = json.dumps([{'Config': 'fixture.json', 'Layers': []}]).encode()
            entry = tarfile.TarInfo('manifest.json')
            entry.size = len(data)
            archive.addfile(entry, io.BytesIO(data))
    write_sums(root)
    return manifest


class InventoryTests(unittest.TestCase):
    def test_every_installed_service_image_and_persistent_volume_is_in_contract(self):
        source = containers()
        source[0]['Config']['Env'].append('PASSWORD=secret')
        backend = next(c for c in source if c['Name'] == '/erpnext-backend')
        worker = next(c for c in source if c['Name'] == '/erpnext-queue-short')
        worker['Mounts'] = copy.deepcopy(backend['Mounts'])
        # Discover a private Board bind from the actual mounted path.
        wp = next(c for c in source if c['Config']['Labels']['com.docker.compose.service'] == 'rootedpsyche-wordpress')
        wp['Mounts'].append({'Type': 'bind', 'Source': '/private/board records',
                             'Destination': '/srv/rootedpsyche-board-supplements', 'RW': False})
        inventory = bundle.make_inventory(source, [])
        self.assertEqual(len(inventory['volumes']), len(bundle.VOLUME_SPECS))
        required = set(inventory['required_payloads'])
        self.assertIn('db/dank-wordpress-all-databases.sql.gz', required)
        self.assertIn('volumes/librechat-mongodb.tgz', required)
        self.assertIn('volumes/librechat-kids-mongodb.tgz', required)
        self.assertIn(bundle.IMAGE_ARCHIVE, required)
        self.assertIn('bind_mounts/runtime-bind-000.tgz', required)
        self.assertEqual(inventory['binds'][0]['source'], '/private/board records')
        serialized = json.dumps(inventory)
        self.assertNotIn('never-serialize-this', serialized)
        self.assertNotIn('PASSWORD', serialized)
        self.assertEqual({r['image_id'] for r in inventory['services']}, {c['Image'] for c in source})
        # Release rehearsal/helper containers can have Labels: null. They are
        # unrelated to the scoped production services and must be ignored.
        source.append({'Name': '/release-helper', 'Config': {'Labels': None}})
        bundle.make_inventory(source, [])

    def test_missing_partial_ambiguous_and_unmapped_sources_fail(self):
        source = containers()
        with self.assertRaisesRegex(ValueError, 'Partially installed'):
            bundle.make_inventory(source[1:], [])
        wp = next(c for c in source if c['Config']['Labels']['com.docker.compose.service'] == 'dank-wordpress')
        with self.assertRaisesRegex(ValueError, 'Ambiguous'):
            bundle.make_inventory(source + [copy.deepcopy(wp)], [])
        source[0]['Mounts'].append({'Type': 'volume', 'Destination': '/unmapped', 'Name': 'extra'})
        # Live SQL data volumes are deliberately covered by dumps, not raw copies.
        source[8]['Mounts'].append({'Type': 'volume', 'Destination': '/unmapped', 'Name': 'extra'})
        with self.assertRaisesRegex(ValueError, 'Unmapped persistent'):
            bundle.make_inventory(source, [])

    def test_absence_is_explicit_and_orphaned_optional_state_is_not_skipped(self):
        source = containers(['core', 'rootedpsyche'])
        inventory = bundle.make_inventory(source, [])
        self.assertEqual(inventory['groups']['dank'], 'not-installed')
        self.assertEqual(inventory['groups']['librechat'], 'not-installed')
        for name in ('docker_librechat_data', 'dank-store-test_dank_wordpress_html', 'rootedops-scheduling_tymeslot_pg'):
            with self.assertRaisesRegex(ValueError, 'Missing source containers'):
                bundle.make_inventory(source, [name])
        # Adult absence is independent of an installed kids instance.
        bundle.make_inventory(containers(['core', 'rootedpsyche', 'librechat-kids']), ['docker_librechat_kids_data'])

    def test_source_drift_refuses_mixing_images_and_data_but_allows_our_pause(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = containers()
            original = bundle.make_inventory(source, [])
            (root / 'meta').mkdir()
            (root / bundle.MANIFEST).write_text(json.dumps(original))
            def inspect(command):
                if command[1:3] == ['ps', '-aq']:
                    return 'fixture-id'
                if command[1] == 'inspect':
                    return json.dumps(source)
                return ''
            with patch.object(bundle, 'checked_output', side_effect=inspect):
                bundle.verify_sources(root, ['docker'])
                source[0]['State']['Running'] = False
                with self.assertRaisesRegex(ValueError, 'changed during backup'):
                    bundle.verify_sources(root, ['docker'])
                bundle.verify_sources(root, ['docker'], allow_stopped=True)
                source[0]['Image'] = 'sha256:' + '9' * 64
                with self.assertRaisesRegex(ValueError, 'changed during backup'):
                    bundle.verify_sources(root, ['docker'], allow_stopped=True)


class ImageSelectionTests(unittest.TestCase):
    def test_published_images_omit_bytes_and_only_used_custom_image_is_archived(self):
        public, custom, unused = ['sha256:' + digit * 64 for digit in ('1', '2', '3')]
        inventory = {'services': [{'project': 'core', 'service': name, 'image_id': image}
                                 for name, image in [('postgres', public), ('documenso', custom), ('erp-worker', custom)]],
                     'required_payloads': [bundle.IMAGE_ARCHIVE]}
        images = [{'Id': image, 'Size': size, 'Os': 'linux', 'Architecture': 'amd64', 'RepoDigests': refs}
                  for image, size, refs in [(public, 5000, ['docker.io/library/postgres@' + public]),
                                            (custom, 7000, []), (unused, 99000, [])]]
        bundle.select_images(inventory, images, lambda ref: {'schemaVersion': 2})
        self.assertEqual([(r['image_id'], r['recovery']) for r in inventory['images']], [(public, 'registry'), (custom, 'archive')])
        self.assertEqual(inventory['image_summary']['archived_uncompressed_bytes'], 7000)
        self.assertEqual(inventory['image_summary']['registry_uncompressed_bytes_omitted'], 5000)
        self.assertEqual(inventory['images'][1]['services'], ['core/documenso', 'core/erp-worker'])

    def test_config_identity_and_multiarch_platform_must_match(self):
        image = {'Id': 'sha256:' + '1' * 64, 'Os': 'linux', 'Architecture': 'amd64'}
        root, arm, amd = ['sha256:' + digit * 64 for digit in ('2', '3', '4')]
        manifests = {'repo@' + root: {'schemaVersion': 2, 'manifests': [
            {'digest': arm, 'platform': {'os': 'linux', 'architecture': 'arm64'}},
            {'digest': amd, 'platform': {'os': 'linux', 'architecture': 'amd64'}}]},
            'repo@' + arm: {'schemaVersion': 2, 'config': {'digest': image['Id']}},
            'repo@' + amd: {'schemaVersion': 2, 'config': {'digest': image['Id']}}}
        self.assertTrue(bundle.registry_matches('repo@' + root, image, manifests.__getitem__))
        manifests['repo@' + amd]['config']['digest'] = arm
        self.assertFalse(bundle.registry_matches('repo@' + root, image, manifests.__getitem__))

    def test_loaded_public_tag_is_resolved_to_immutable_matching_digest(self):
        image = {'Id': 'sha256:' + '1' * 64, 'Size': 10, 'Os': 'linux', 'Architecture': 'amd64',
                 'RepoDigests': [], 'RepoTags': ['postgres:16']}
        digest = 'postgres@sha256:' + '2' * 64
        inventory = {'services': [{'project': 'core', 'service': 'postgres', 'image_id': image['Id']}],
                     'required_payloads': [bundle.IMAGE_ARCHIVE]}
        def inspect(reference):
            if reference != digest:
                raise RuntimeError('Config digest is not a registry manifest')
            return {'schemaVersion': 2, 'config': {'digest': image['Id']}}
        bundle.select_images(inventory, [image], inspect, lambda tag: [digest])
        self.assertEqual(inventory['images'][0]['reference'], digest)
        self.assertIsNone(inventory['image_archive'])
        self.assertNotIn(bundle.IMAGE_ARCHIVE, inventory['required_payloads'])

    def test_loaded_public_index_identity_avoids_unnecessary_archival(self):
        image = {'Id': 'sha256:' + '1' * 64, 'Size': 10, 'Os': 'linux', 'Architecture': 'amd64',
                 'RepoDigests': [], 'RepoTags': ['postgres:16']}
        inventory = {'services': [{'project': 'core', 'service': 'postgres', 'image_id': image['Id']}],
                     'required_payloads': [bundle.IMAGE_ARCHIVE]}
        bundle.select_images(inventory, [image], lambda ref: {'schemaVersion': 2}, lambda tag: [])
        self.assertEqual(inventory['images'][0]['reference'], 'postgres@' + image['Id'])
        self.assertIsNone(inventory['image_archive'])

    def test_wrong_registry_content_never_silently_becomes_a_large_archive(self):
        image = {'Id': 'sha256:' + '1' * 64, 'Size': 10, 'Os': 'linux', 'Architecture': 'amd64',
                 'RepoDigests': ['postgres@sha256:' + '2' * 64]}
        inventory = {'services': [{'project': 'core', 'service': 'postgres', 'image_id': image['Id']}],
                     'required_payloads': []}
        with self.assertRaisesRegex(ValueError, 'no automatic image-archive fallback'):
            bundle.select_images(inventory, [image], lambda ref: {'schemaVersion': 2, 'config': {'digest': 'sha256:' + '3' * 64}})

    def test_local_build_repository_digest_does_not_mean_image_was_published(self):
        image = {'Id': 'sha256:' + '1' * 64, 'Size': 10, 'Os': 'linux', 'Architecture': 'amd64',
                 'RepoDigests': ['local-build@sha256:' + '1' * 64]}
        inventory = {'services': [{'project': 'core', 'service': 'documenso', 'image_id': image['Id']}],
                     'required_payloads': []}
        def missing(reference):
            raise bundle.RegistryNotPublished('never pushed')
        bundle.select_images(inventory, [image], missing)
        self.assertEqual(inventory['images'][0]['recovery'], 'archive')
        self.assertIn(bundle.IMAGE_ARCHIVE, inventory['required_payloads'])

    def test_registry_not_published_is_distinct_from_outage_rate_limit_or_bad_response(self):
        for error, expected in [
            (subprocess.CalledProcessError(1, ['docker'], stderr='denied: requested access to the resource is denied'), bundle.RegistryNotPublished),
            (subprocess.CalledProcessError(1, ['docker'], stderr='toomanyrequests: retry later'), RuntimeError),
            (subprocess.TimeoutExpired(['docker'], 30), RuntimeError),
        ]:
            with patch.object(bundle.subprocess, 'run', side_effect=error):
                with self.assertRaises(expected) as caught:
                    bundle.registry_json(['docker'], '/anonymous', 'repo@sha256:' + '1' * 64)
                if expected == RuntimeError:
                    self.assertNotIsInstance(caught.exception, bundle.RegistryNotPublished)


class CompletenessTests(unittest.TestCase):
    def test_missing_archive_even_after_rewriting_checksums_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_fixture(root)
            bundle.validate_bundle(root)
            (root / 'volumes/librechat-kids-mongodb.tgz').unlink()
            write_sums(root)
            with self.assertRaisesRegex(ValueError, 'missing from SHA256SUMS'):
                bundle.validate_bundle(root)

    def test_contract_cannot_delete_required_payload_or_group_services(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            m = write_fixture(root)
            m['required_payloads'].remove('db/dank-wordpress-all-databases.sql.gz')
            (root / bundle.MANIFEST).write_text(json.dumps(m))
            write_sums(root)
            with self.assertRaisesRegex(ValueError, 'omits required'):
                bundle.validate_bundle(root)
            m = write_fixture(root)
            m['services'].pop()
            (root / bundle.MANIFEST).write_text(json.dumps(m))
            write_sums(root)
            with self.assertRaisesRegex(ValueError, 'service inventory'):
                bundle.validate_bundle(root)

    def test_old_snapshot_and_corrupt_image_archive_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, 'fresh format-2'):
                bundle.validate_bundle(root)
            write_fixture(root)
            (root / bundle.IMAGE_ARCHIVE).write_bytes(b'invalid gzip')
            write_sums(root)
            with self.assertRaises((OSError, ValueError)):
                bundle.validate_bundle(root)

    def test_prepare_images_pins_custom_and_floating_images_without_starting_apps(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            backup = root / 'backup'
            manifest = write_fixture(backup)
            output = root / 'test'
            output.mkdir()
            (output / 'TEST_ENVIRONMENT').write_text('rootedops-full-test')
            for project in ('core', 'rootedpsyche', 'dank', 'tymeslot', 'rallly'):
                path = output / ('rallly/compose.yml' if project == 'rallly' else project + '.yml')
                path.parent.mkdir(exist_ok=True)
                services = {r['service']: {'image': 'floating:latest', 'build': {'context': '.'},
                                          'ports': ['127.0.0.1:9999:80']}
                            for r in manifest['services'] if r['project'] == project}
                if project == 'core':
                    services['erpnext-apps-init'] = {'build': {'context': '.'}}
                path.write_text(yaml.safe_dump({'services': services, 'networks': {'default': {'internal': True}}}))
            def output_for(command):
                if command[1:3] == ['ps', '-aq']:
                    return ''
                name = command[-1]
                return name if name.startswith('sha256:') else 'sha256:' + name.split(':')[1]
            with patch.object(bundle, 'checked_output', side_effect=output_for), patch.object(bundle.subprocess, 'run') as run:
                bundle.prepare_images(output, backup)
                commands = [c.args[0] for c in run.call_args_list]
                self.assertTrue(any(c[:3] == ['docker', 'image', 'load'] for c in commands))
                self.assertFalse(any('up' in c or 'start' in c or 'build' in c for c in commands))
                bundle.verify_images(output, backup)
                core = yaml.safe_load((output / 'core.yml').read_text())
                for service in core['services'].values():
                    self.assertNotIn('build', service)
                    self.assertEqual(service['pull_policy'], 'never')
                self.assertEqual(core['services']['erpnext-apps-init']['image'], core['services']['erpnext-backend']['image'])
                (output / 'core.yml').write_text('tampered')
                with self.assertRaisesRegex(ValueError, 'no longer matches'):
                    bundle.verify_images(output, backup)


FAKE_DOCKER = r'''#!/usr/bin/env python3
import io,json,os,pathlib,sys,tarfile
args=sys.argv[1:]; root=pathlib.Path(os.environ['FIXTURE_ROOT'])
state=json.loads((root/'state.json').read_text())
with (root/'events').open('a') as f:f.write(json.dumps(args)+'\n')
if args[0]=='--config':args=args[2:]
def archive(path,filename='fixture',data=b'synthetic'):
 path.parent.mkdir(parents=True,exist_ok=True)
 with tarfile.open(path,'w:gz') as t:
  m=tarfile.TarInfo(filename);m.size=len(data);t.addfile(m,io.BytesIO(data))
if args[:2]==['ps','-aq']: print('\n'.join(c['Name'].lstrip('/') for c in state))
elif args[0]=='inspect':
 if '-f' in args:print('true')
 else:print(json.dumps([c for c in state if c['Name'].lstrip('/') in args[1:]]))
elif args[:2]==['volume','ls']: print('\n'.join(m['Name'] for c in state for m in c['Mounts'] if m['Type']=='volume'))
elif args[:2]==['volume','inspect']:pass
elif args[:2]==['image','inspect']:
 result=[]
 for image in args[2:]:
  custom=any(c['Image']==image and c['Name'] in ('/documenso','/erpnext-backend') for c in state)
  if os.environ.get('REGISTRY_ONLY'):custom=False
  result.append({'Id':image,'Size':4096,'Os':'linux','Architecture':'amd64','RepoDigests':['docker.io/fixture/'+('unpublished' if custom else 'runtime')+'@'+image]})
 print(json.dumps(result))
elif args[:2]==['manifest','inspect']:
 if os.environ.get('FAIL_REGISTRY'):sys.exit(25)
 if '/unpublished@' in args[-1]:print('denied: requested access to the resource is denied',file=sys.stderr);sys.exit(26)
 print(json.dumps({'schemaVersion':2,'config':{'digest':args[-1].split('@')[1]}}))
elif args[:2]==['image','save']:
 if os.environ.get('FAIL_IMAGES'):sys.exit(22)
 with tarfile.open(fileobj=sys.stdout.buffer,mode='w|') as t:
  data=json.dumps([{'Config':v.split(':')[1]+'.json','Layers':[]} for v in args[2:]]).encode()
  m=tarfile.TarInfo('manifest.json');m.size=len(data);t.addfile(m,io.BytesIO(data))
elif args[:2]==['image','ls'] or args[0] in ('version','ps'):print('synthetic metadata')
elif args[0] in ('stop','start'):
 if args[0]=='start' and args[1]==os.environ.get('FAIL_START'):sys.exit(24)
 for c in state:
  if c['Name'].lstrip('/')==args[1]:c['State']['Running']=args[0]=='start'
 (root/'state.json').write_text(json.dumps(state))
elif args[0]=='exec':
 if 'bench' in args:print('frappe 16.fixture\nerpnext 16.fixture')
 else:print('-- synthetic SQL dump\nCREATE TABLE fixture(id integer);')
elif args[0]=='run':
 mounts=[args[i+1] for i,v in enumerate(args) if v=='-v']
 dest=next(pathlib.Path(m.rsplit(':',1)[0]) for m in mounts if m.endswith(':/backup'))
 if any(m.endswith(':/volume:ro') for m in mounts):
  filename=args[-1].split('/backup/')[1].split()[0]
  if filename==os.environ.get('FAIL_ARCHIVE'):sys.exit(23)
  archive(dest/filename)
 elif args[-1].endswith('.tgz'):archive(dest/args[-1],'payload')
 elif 'rallly-selfhosted-env.tgz' in args[-1]:archive(dest/'rallly-selfhosted-env.tgz','.env',b'SECRET_PASSWORD=fixture\n')
 else:raise SystemExit('unexpected docker helper')
else:raise SystemExit('unexpected docker command')
'''


FAKE_RCLONE = r'''#!/usr/bin/env python3
import os,pathlib,shutil,sys
root=pathlib.Path(os.environ['FIXTURE_ROOT']);args=sys.argv[1:]
with (root/'remote-events').open('a') as f:f.write(' '.join(args)+'\n')
if args[0]=='listremotes':print('fixture:')
elif args[0]=='copy':shutil.copytree(args[-2],root/'remote',symlinks=True)
elif args[0] in ('mkdir','check'):pass
else:raise SystemExit('unexpected rclone action')
'''


class NightlyScriptTests(unittest.TestCase):
    def fixture(self, root):
        import shutil
        checkout = root / 'RootedOps'
        for file in ('backup/backup-stack.sh', 'backup/volume-tools.sh', 'scripts/recovery_bundle.py',
                     'docker/docker-compose.yml', 'docker/scheduling/tymeslot.compose.yml'):
            dest = checkout / file
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / file, dest)
        rallly = checkout / 'docker/scheduling/rallly-selfhosted/.env'
        rallly.parent.mkdir()
        rallly.write_text('SECRET_PASSWORD=fixture\n')
        bin_dir = root / 'bin'
        bin_dir.mkdir()
        for name, text in [('docker', FAKE_DOCKER), ('rclone', FAKE_RCLONE)]:
            p = bin_dir / name
            p.write_text(text)
            p.chmod(0o755)
        values = {'DOCKER_BIN': str(bin_dir / 'docker'), 'RCLONE_REMOTE': 'fixture',
                  'LOCAL_STAGING_PARENT': str(root / 'stage'), 'SKIP_BACKUP_PRUNE': 'true'}
        for prefix in ('SIG', 'MP_BRIDGE', 'LISTMONK', 'NC', 'DOCUMENSO'):
            for key in ('DB_NAME', 'DB_USER', 'DB_PASSWORD'):
                values[prefix + '_' + key] = 'fixture'
        for key in ('ERPNEXT_DB_ROOT_PASSWORD', 'ROOTEDPSYCHE_WP_DB_ROOT_PASSWORD', 'DANK_WP_DB_ROOT_PASSWORD'):
            values[key] = 'fixture'
        (checkout / '.env').write_text(''.join(k + '=' + v + '\n' for k, v in values.items()))
        state = containers()
        # Preserve a deliberately stopped app; the backup must not start it.
        next(c for c in state if c['Name'] == '/librechat-kids')['State']['Running'] = False
        (root / 'state.json').write_text(json.dumps(state))
        return checkout, dict(os.environ, FIXTURE_ROOT=str(root), PATH=str(bin_dir) + ':' + os.environ['PATH'])

    def test_nightly_job_produces_complete_bundle_and_resumes_only_running_services(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checkout, env = self.fixture(root)
            result = subprocess.run(['bash', str(checkout / 'backup/backup-stack.sh')], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            backup = next(p for p in (root / 'remote').iterdir() if p.is_dir() and not p.is_symlink())
            inventory = bundle.validate_bundle(backup)
            self.assertEqual(inventory['groups']['dank'], 'installed')
            self.assertEqual(inventory['image_summary']['archived_images'], 2)
            self.assertGreater(inventory['image_summary']['registry_images'], 2)
            self.assertGreater(inventory['image_summary']['stored_archive_bytes'], 0)
            events = [json.loads(line) for line in (root / 'events').read_text().splitlines()]
            saved = next(c for c in events if c[:2] == ['image', 'save'])
            self.assertEqual(set(saved[2:]), {r['image_id'] for r in inventory['images'] if r['recovery'] == 'archive'})
            self.assertFalse(set(saved[2:]) & {r['image_id'] for r in inventory['images'] if r['recovery'] == 'registry'})
            self.assertNotIn(['start', 'librechat-kids'], events)
            self.assertIn(['stop', 'librechat-mongodb'], events)
            self.assertIn(['start', 'librechat-mongodb'], events)
            self.assertLess(events.index(['stop', 'n8n']), next(i for i,c in enumerate(events) if c[0]=='exec' and 'pg_dump' in c))
            self.assertLess(events.index(['start', 'librechat-mongodb']), events.index(['start', 'librechat']))
            for row in inventory['services']:
                state = next(c for c in json.loads((root / 'state.json').read_text()) if c['Name'].lstrip('/') == row['container'])
                self.assertEqual(state['State']['Running'], row['running'])
            self.assertEqual((backup / bundle.MANIFEST).stat().st_mode & 0o777, 0o600)

    def test_failed_volume_resumes_apps_and_never_uploads_or_prunes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checkout, env = self.fixture(root)
            env['FAIL_ARCHIVE'] = 'librechat-mongodb.tgz'
            result = subprocess.run(['bash', str(checkout / 'backup/backup-stack.sh')], env=env, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((root / 'remote').exists())
            self.assertEqual((root / 'remote-events').read_text().splitlines(), ['listremotes'])
            events = [json.loads(line) for line in (root / 'events').read_text().splitlines()]
            self.assertIn(['start', 'n8n'], events)
            self.assertIn(['start', 'librechat-mongodb'], events)
            self.assertNotIn(['start', 'librechat-kids'], events)

    def test_failed_restart_retries_and_prevents_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checkout, env = self.fixture(root)
            env['FAIL_START'] = 'n8n'
            result = subprocess.run(['bash', str(checkout / 'backup/backup-stack.sh')], env=env, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((root / 'remote').exists())
            events = [json.loads(line) for line in (root / 'events').read_text().splitlines()]
            self.assertEqual(events.count(['start', 'n8n']), 2)

    def test_image_export_failure_happens_before_application_pause(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checkout, env = self.fixture(root)
            env['FAIL_IMAGES'] = '1'
            result = subprocess.run(['bash', str(checkout / 'backup/backup-stack.sh')], env=env, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            events = [json.loads(line) for line in (root / 'events').read_text().splitlines()]
            self.assertFalse(any(c[0] == 'stop' for c in events))
            self.assertFalse((root / 'remote').exists())

    def test_registry_only_snapshot_omits_image_archive_entirely(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checkout, env = self.fixture(root)
            env['REGISTRY_ONLY'] = '1'
            result = subprocess.run(['bash', str(checkout / 'backup/backup-stack.sh')], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            backup = next(p for p in (root / 'remote').iterdir() if p.is_dir() and not p.is_symlink())
            inventory = bundle.validate_bundle(backup)
            self.assertIsNone(inventory['image_archive'])
            self.assertEqual(inventory['image_summary']['stored_archive_bytes'], 0)
            self.assertFalse((backup / bundle.IMAGE_ARCHIVE).exists())
            events = [json.loads(line) for line in (root / 'events').read_text().splitlines()]
            self.assertFalse(any(c[:2] == ['image', 'save'] for c in events))

    def test_registry_outage_never_inflates_backup_or_pauses_apps(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checkout, env = self.fixture(root)
            env['FAIL_REGISTRY'] = '1'
            result = subprocess.run(['bash', str(checkout / 'backup/backup-stack.sh')], env=env, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('no automatic image-archive fallback', result.stderr)
            events = [json.loads(line) for line in (root / 'events').read_text().splitlines()]
            self.assertFalse(any(c[0] == 'stop' or c[:2] == ['image', 'save'] for c in events))
            self.assertFalse((root / 'remote').exists())

    def test_image_plan_reports_selection_without_exports_pauses_or_uploads(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checkout, env = self.fixture(root)
            env['BACKUP_IMAGE_PLAN_ONLY'] = 'true'
            result = subprocess.run(['bash', str(checkout / 'backup/backup-stack.sh')], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('Image selection:', result.stdout)
            self.assertIn('ARCHIVE core/documenso', result.stdout)
            self.assertIn('REGISTRY ', result.stdout)
            self.assertIn('Image plan only:', result.stdout)
            events = [json.loads(line) for line in (root / 'events').read_text().splitlines()]
            self.assertFalse(any(c[0] in ('stop', 'start', 'exec') or c[:2] == ['image', 'save'] for c in events))
            self.assertFalse((root / 'remote').exists())

    def test_cron_and_manual_runs_cannot_overlap(self):
        import fcntl
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checkout, env = self.fixture(root)
            (root / 'stage').mkdir()
            with (root / 'stage/.rootedops-backup.lock').open('w') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                result = subprocess.run(['bash', str(checkout / 'backup/backup-stack.sh')], env=env, capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('Another RootedOps backup', result.stderr)
                self.assertFalse((root / 'events').exists())
