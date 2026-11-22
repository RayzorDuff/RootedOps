"""Standalone hostname configuration on the deployed customer-sync baseline."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class HostnameConfiguration(unittest.TestCase):
    def test_existing_private_config_and_transport_only_rollback(self):
        source = (ROOT / 'scripts/commerce-configure-woo-signup.sh').read_text()
        code = source.split('"$python" -c \'', 1)[1].split('\n\' "$site"', 1)[0]
        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory) / 'erp.danks.store'
            site.mkdir()
            path = site / 'site_config.json'
            original = {'db_password': 'synthetic-db', 'commerce_customer_sync': {
                'enabled': True, 'production_erp_pilot': True,
                'woo_site': 'shop-test.danks.store', 'woo_customer_ids': [3],
                'woo_authorization': 'Basic synthetic', 'project_enabled': True,
                'provision_new_woo_customers': True}}
            path.write_text(json.dumps(original))
            def run(mode):
                return subprocess.run([sys.executable, '-c', code, str(site), mode],
                                      text=True, capture_output=True)
            self.assertEqual(run('hostname').returncode, 0)
            updated = json.loads(path.read_text())
            expected = json.loads(json.dumps(original))
            expected['commerce_customer_sync'].update(
                woo_origin='https://dankmushrooms.net', same_woo_installation=True)
            self.assertEqual(updated, expected)
            backup = path.with_name('site_config.json.before-standalone-hostname')
            self.assertEqual(json.loads(backup.read_text()), original)
            self.assertEqual(os.stat(backup).st_mode & 0o777, 0o600)
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
            self.assertEqual(run('hostname').returncode, 0)
            updated['newer_setting'] = 'preserve after rollback'
            path.write_text(json.dumps(updated))
            self.assertEqual(run('restore_hostname').returncode, 0)
            restored = json.loads(path.read_text())
            self.assertEqual(restored['newer_setting'], updated['newer_setting'])
            self.assertEqual(restored['commerce_customer_sync']['woo_origin'],
                             'https://shop-test.danks.store')
            self.assertEqual(json.loads(backup.read_text()), original)
            restored['commerce_customer_sync']['woo_origin'] = 'https://unknown.invalid'
            path.write_text(json.dumps(restored))
            before = path.read_text()
            self.assertNotEqual(run('hostname').returncode, 0)
            self.assertEqual(path.read_text(), before)
