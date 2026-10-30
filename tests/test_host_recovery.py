import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import host_recovery as recovery

class HostRecoveryTests(unittest.TestCase):
 def test_app_fetch_supports_exact_commit_and_tag_without_overwriting(self):
    import subprocess
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory);source=root/'source';source.mkdir()
        def git(*args):return subprocess.check_output(['git',*args],text=True,stderr=subprocess.DEVNULL).strip()
        git('init','-q',str(source));git('-C',str(source),'config','user.name','Synthetic CI')
        git('-C',str(source),'config','user.email','synthetic@example.invalid')
        (source/'version').write_text('original');git('-C',str(source),'add','version');git('-C',str(source),'commit','-qm','original')
        original=git('-C',str(source),'rev-parse','HEAD');git('-C',str(source),'tag','reviewed-version')
        (source/'version').write_text('later');git('-C',str(source),'commit','-qam','later')
        for number,ref in enumerate((original,'reviewed-version')):
            target=root/str(number)
            result=subprocess.run(['bash',str(ROOT/'docker/fetch-frappe-app.sh'),str(target),source.as_uri(),ref],capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr.decode())
            self.assertEqual(git('-C',str(target),'rev-parse','HEAD'),original)
            self.assertEqual((target/'version').read_text(),'original')
            retry=subprocess.run(['bash',str(ROOT/'docker/fetch-frappe-app.sh'),str(target),source.as_uri(),ref],capture_output=True)
            self.assertNotEqual(retry.returncode,0)
            self.assertEqual((target/'version').read_text(),'original')

 def test_distinct_generated_secrets_and_crypto_shapes(self):
    import base64
    a,b=recovery.environment(),recovery.environment()
    passwords=[v for k,v in a.items() if k.endswith('_DB_PASSWORD')]
    self.assertEqual(len(passwords),len(set(passwords)))
    self.assertNotEqual(a['N8N_ENCRYPTION_KEY'],b['N8N_ENCRYPTION_KEY'])
    self.assertEqual(len(bytes.fromhex(a['LIBRECHAT_CREDS_IV'])),16)
    self.assertEqual(len(base64.b64decode(a['TYMESLOT_DATA_ENCRYPTION_KEY'])),32)
    for key in ('ECWID_SECRET_TOKEN','CLOVER_ACCESS_TOKEN','OPENROUTER_KEY','ERPNEXT_API_SECRET'):
        self.assertEqual(a[key],'')
 def test_hostname_suffix_generation(self):
    default=recovery.hosts_for_suffix('-test')
    second=recovery.hosts_for_suffix('-test2')
    production=recovery.hosts_for_suffix('')
    self.assertEqual(default['erpnext'],'erp-test.danks.store')
    self.assertEqual(second['erpnext'],'erp-test2.danks.store')
    self.assertEqual(second['tymeslot'],'schedule-test2.rootedpsyche.org')
    self.assertEqual(production['erpnext'],'erp.danks.store')
    self.assertEqual(production['rootedpsyche-wordpress'],'www.rootedpsyche.org')
    for suffix in ('test2','-bad_name','-','-Test'):
        with self.assertRaises(ValueError): recovery.hosts_for_suffix(suffix)
    with tempfile.TemporaryDirectory() as d:
        path=Path(d);(path/'receipt.json').write_text('{"hostname_suffix":"-test2"}')
        self.assertEqual(recovery.deployment_hosts(path),second)
 def test_private_write_refuses_overwrite(self):
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'private/.env';recovery.private_write(path,'secret')
        self.assertEqual(path.stat().st_mode&0o777,0o600)
        with self.assertRaises(FileExistsError):recovery.private_write(path,'replacement')
        self.assertEqual(path.read_text(),'secret')
 def test_render_isolates_and_resolves_build_and_mount_paths(self):
    source=Path('/arbitrary/home/RootedOps/docker')
    config={'services':{'app':{'container_name':'production','build':{'context':'..'},'environment':{'FLAG':False},'ports':['8080:80'],'volumes':['../data:/data:rw','state:/state']}},'volumes':{'state':None}}
    result=recovery.transform(config,source,'test')
    app=result['services']['app']
    self.assertNotIn('container_name',app)
    self.assertEqual(app['ports'],['127.0.0.1:8080:80'])
    self.assertEqual(app['build']['context'],'/arbitrary/home/RootedOps')
    self.assertTrue(app['volumes'][0].startswith('/arbitrary/home/RootedOps/data:'))
    self.assertEqual(app['environment']['FLAG'],'false')
    self.assertTrue(result['networks']['default']['internal'])
    self.assertEqual(config['services']['app']['container_name'],'production')
 def test_all_declared_hosts_have_matching_vhosts(self):
    import re
    for name,host in recovery.HOSTS.items():
        path=ROOT/'nginx'/(name+'.conf')
        self.assertTrue(path.is_file(),str(path))
        self.assertIn(host,re.findall(r'server_name\s+([^;]+);',path.read_text())[0].split())
 def test_source_recovery_retains_required_tree_and_grav_retirement(self):
    import yaml
    for path in ('linode_bootstrap.sh','backup/backup-stack.sh','erpnext/apps/rootedops_commerce/pyproject.toml','.github/workflows/commerce-foundation.yml'):
        self.assertTrue((ROOT/path).is_file(),path)
    self.assertNotIn('grav',yaml.safe_load((ROOT/'docker/docker-compose.yml').read_text())['services'])
    self.assertFalse((ROOT/'nginx/grav.conf').exists())

class FullRestoreGuards(unittest.TestCase):
 def test_redaction_acknowledgement_never_ignores_missing_or_changed_payloads(self):
    import hashlib
    import full_restore
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory);(root/'db').mkdir()
        payload=root/'db/mushroomprocess-bridge-postgres.sql.gz';payload.write_bytes(b'synthetic')
        manifest='0'*64+'  meta/.env\n'+hashlib.sha256(payload.read_bytes()).hexdigest()+'  db/'+payload.name+'\n'
        (root/'SHA256SUMS').write_text(manifest)
        selected=full_restore.Recovery(root/'test',root,['mushroomprocess'],allow_removed_secret_metadata=True)
        selected.verify_checksums()
        self.assertEqual(selected.removed_secret_metadata,['meta/.env'])
        self.assertEqual((root/'SHA256SUMS').read_text(),manifest)
        payload.write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError,'checksum mismatch'):selected.verify_checksums()
        payload.unlink()
        with self.assertRaisesRegex(ValueError,'Missing or unsafe'):selected.verify_checksums()
        (root/'SHA256SUMS').write_text('0'*64+'  meta/.env\n')
        with self.assertRaisesRegex(ValueError,'Selected payload'):selected.verify_checksums()

 def test_selected_recovery_requires_only_private_allowlisted_keys(self):
    import full_restore
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory)
        self.assertEqual(full_restore.Recovery(root/'test',root,['mushroomprocess','erpnext']).encryption_source(),{})
        keys=root/'keys';keys.write_text('N8N_ENCRYPTION_KEY=synthetic\n');keys.chmod(0o600)
        selected=full_restore.Recovery(root/'test',root,['n8n'],key_file=keys)
        self.assertEqual(selected.encryption_source(),{'N8N_ENCRYPTION_KEY':'synthetic'})
        keys.write_text('N8N_ENCRYPTION_KEY=synthetic\nCLOVER_ACCESS_TOKEN=unwanted\n')
        with self.assertRaisesRegex(ValueError,'exactly'):selected.encryption_source()
        keys.chmod(0o644)
        with self.assertRaisesRegex(ValueError,'private permissions'):selected.encryption_source()
        with self.assertRaises(ValueError):full_restore.Recovery(root/'test',root,key_file=keys)

 def test_component_selection_omits_unrelated_data_and_pending_queues(self):
    import full_restore
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory);backup=root/'backup';backup.mkdir()
        (backup/'volumes').mkdir();(backup/'bind_mounts').mkdir()
        for name in ('erpnext_apps.tgz','erpnext_sites.tgz','erpnext_logs.tgz','erpnext_redis_queue_data.tgz','rootedpsyche-wordpress-html.tgz','rallly-selfhosted_db-data.tgz'):
            (backup/'volumes'/name).touch()
        (backup/'bind_mounts/production-routing.tgz').touch()
        selected=full_restore.Recovery(root/'test',backup,['erpnext'])
        self.assertEqual({p.name for p in selected.archives('volumes','*.tgz')},{'erpnext_apps.tgz','erpnext_sites.tgz'})
        self.assertEqual(selected.bind_archives(),[])
        full=full_restore.Recovery(root/'test',backup)
        self.assertEqual(len(full.archives('volumes','*.tgz')),6)
        self.assertEqual(len(full.bind_archives()),1)
        with self.assertRaises(ValueError):full_restore.Recovery(root/'test',backup,[])
        with self.assertRaises(ValueError):full_restore.Recovery(root/'test',backup,['unknown'])

 def test_missing_selected_archive_or_source_site_refuses_before_mutation(self):
    from unittest.mock import patch
    import full_restore
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory);env=root/'test';backup=root/'backup';env.mkdir();backup.mkdir()
        (env/'TEST_ENVIRONMENT').write_text('rootedops-full-test\n')
        (backup/'SHA256SUMS').touch();(backup/'db').mkdir();(backup/'volumes').mkdir()
        selected=full_restore.Recovery(env,backup,['erpnext'])
        with patch.object(full_restore.subprocess,'run') as run:
            with self.assertRaisesRegex(ValueError,'Missing selected'):selected.run('erp.example.invalid')
            run.assert_not_called()
            for name in full_restore.COMPONENT_FILES['erpnext']:
                (backup/('db' if name.endswith('.sql.gz') else 'volumes')/name).touch()
            with self.assertRaisesRegex(ValueError,'source-site required'):selected.run(None)
            run.assert_not_called()
        self.assertFalse((env/'RESTORE_STARTED').exists())

 def test_selected_run_never_restores_other_services_or_copies_external_keys(self):
    import gzip,json
    from types import SimpleNamespace
    from unittest.mock import Mock
    import full_restore
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory);env=root/'test';backup=root/'backup';env.mkdir()
        for name in ('db','volumes','meta','bind_mounts'):(backup/name).mkdir(parents=True)
        (env/'.env').write_text('MP_BRIDGE_DB_NAME=mushroomprocess_test\nMP_BRIDGE_DB_USER=tester\nMP_BRIDGE_DB_PASSWORD=generated-test-password\nCLOVER_ACCESS_TOKEN=\nN8N_ENCRYPTION_KEY=generated-key\n')
        (backup/'meta/.env').write_text('MP_BRIDGE_DB_PASSWORD=old-source-password\nCLOVER_ACCESS_TOKEN=synthetic-source-token\nN8N_ENCRYPTION_KEY=synthetic-preserved-key\nAPPSMITH_ENCRYPTION_PASSWORD=synthetic-password\nAPPSMITH_ENCRYPTION_SALT=synthetic-salt\n')
        with gzip.open(backup/'db/mushroomprocess-bridge-postgres.sql.gz','wb') as f:f.write(b'-- synthetic empty dump\n')
        for name in ('erpnext-all-databases.sql.gz','rootedpsyche-wordpress-all-databases.sql.gz'):(backup/'db'/name).touch()
        for name in ('n8n_data.tgz','appsmith_stacks.tgz','rallly-selfhosted_db-data.tgz'):(backup/'volumes'/name).touch()
        keys=env/'decryption.keys';keys.write_text('N8N_ENCRYPTION_KEY=synthetic-preserved-key\nAPPSMITH_ENCRYPTION_PASSWORD=synthetic-password\nAPPSMITH_ENCRYPTION_SALT=synthetic-salt\n');keys.chmod(0o600)
        selected=full_restore.Recovery(env,backup,['mushroomprocess','n8n','appsmith'],key_file=keys)
        selected.preflight=Mock();selected.dc=Mock(return_value=SimpleNamespace(stdout=''))
        selected.ready=Mock();selected.sql=Mock();selected.volume=Mock()
        selected.run(None)
        self.assertEqual({c.args[3] for c in selected.volume.call_args_list},{'n8n_data.tgz','appsmith_stacks.tgz'})
        self.assertEqual([c.args[1] for c in selected.sql.call_args_list],['mushroomprocess-bridge-postgres.sql.gz'])
        self.assertEqual([c.args for c in selected.dc.call_args_list],[('core','up','-d','mushroomprocess-bridge-postgres')])
        values=full_restore.read_env(env/'.env')
        self.assertEqual(values['MP_BRIDGE_DB_PASSWORD'],'generated-test-password')
        self.assertEqual(values['CLOVER_ACCESS_TOKEN'],'')
        self.assertEqual(values['N8N_ENCRYPTION_KEY'],'synthetic-preserved-key')
        self.assertEqual(list((env/'restored-bind-mounts').iterdir()),[])
        report=json.loads((env/'restore-receipt.json').read_text())
        self.assertEqual(report['selected_components'],['appsmith','mushroomprocess','n8n'])
        self.assertFalse(report['apps_started'])

 def test_existing_host_is_refused_before_any_restore_mutation(self):
    from unittest.mock import patch
    import full_restore
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory);env=root/'test';backup=root/'backup';env.mkdir();backup.mkdir()
        (env/'TEST_ENVIRONMENT').write_text('rootedops-full-test\n')
        (backup/'SHA256SUMS').write_text('')
        recovery=full_restore.Recovery(env,backup)
        with patch.object(full_restore.subprocess,'run') as run, patch.object(full_restore.subprocess,'check_output',return_value='existing-container\n'):
            with self.assertRaisesRegex(ValueError,'new host'):
                recovery.run(None)
            self.assertFalse((env/'RESTORE_STARTED').exists())
            self.assertTrue(all(call.args[0][0]=='sha256sum' for call in run.call_args_list))
