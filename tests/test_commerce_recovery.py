import gzip
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT/'scripts'/f'{name}.py')
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

staging = module('commerce_staging')
restore = module('commerce_restore')

class RecoveryTests(unittest.TestCase):
    def test_fresh_render_and_postgres_preflight(self):
        import yaml
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); env = root/'env'; backup = root/'backup'
            staging.render(env)
            (backup/'db').mkdir(parents=True)
            with gzip.open(backup/'db/mushroomprocess-bridge-postgres.sql.gz', 'wb') as f:
                f.write(b'CREATE TABLE synthetic (id int);\n')
            values = restore.preflight(env, backup, ['mushroomprocess'], None)
            self.assertEqual(values['ERPNEXT_SITE_NAME'], 'erp-test.danks.store')
            config = yaml.safe_load((env/'compose.yml').read_text())
            self.assertNotIn('minecraft-bedwars', config['services'])
            self.assertNotIn('listmonk', config['services'])
            self.assertEqual(values['ERPNEXT_HTTP_PORT'], '8086')
            for service in config['services'].values():
                for mount in service.get('volumes', []):
                    if isinstance(mount, dict):
                        self.assertTrue(mount['volume']['nocopy'])
            config['services']['n8n']['ports'] = ['5678:5678']
            (env/'compose.yml').write_text(yaml.safe_dump(config))
            with self.assertRaisesRegex(ValueError, 'loopback'):
                restore.preflight(env, backup, ['mushroomprocess'], None)

    def test_missing_or_corrupt_backup_fails_before_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); env=root/'env'; backup=root/'backup'
            staging.render(env); (backup/'db').mkdir(parents=True)
            with self.assertRaisesRegex(ValueError, 'Missing required'):
                restore.preflight(env, backup, ['mushroomprocess'], None)
            (backup/'db/mushroomprocess-bridge-postgres.sql.gz').write_bytes(b'not gzip')
            with self.assertRaises(OSError):
                restore.preflight(env, backup, ['mushroomprocess'], None)
            self.assertFalse((env/'RESTORE_STARTED').exists())

    def test_copy_count_validation_does_not_count_escaped_newlines(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'dump.gz'
            with gzip.open(path, 'wb') as f:
                f.write(b'COPY public.example (id, description) FROM stdin;\n1\tText with \\n escape\n2\tAnother\n\\.\n')
            self.assertEqual(restore.copy_counts(path), {'example': 2})
            with gzip.open(path, 'wb') as f:
                f.write(b'COPY public.example (id) FROM stdin;\n1\n')
            with self.assertRaisesRegex(ValueError, 'Unterminated'):
                restore.copy_counts(path)

    def test_nginx_defaults_are_explicit_test_hosts(self):
        import re
        for path in (ROOT/'nginx').glob('*.conf'):
            names = re.findall(r'server_name\s+([^;]+);', path.read_text())
            self.assertTrue(names, path.name)
            for name in ' '.join(names).split():
                self.assertRegex(name, r'^[a-z0-9-]+-test\.danks\.store$', path.name)
