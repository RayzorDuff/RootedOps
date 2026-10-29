#!/usr/bin/env python3
"""Install a fresh, private-credential WooCommerce test shop. No merchant setup."""
import argparse
import json
from pathlib import Path
import secrets
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]


def bootstrap(environment):
    from commerce_restore import read_env
    environment = environment.resolve()
    env = read_env(environment/'.env')
    if env.get('ERPNEXT_SITE_NAME') != 'erp-test.danks.store':
        raise ValueError('Only the authorized commerce test environment is supported')
    credentials = environment/'private/wordpress-credentials.json'
    if credentials.exists():
        raise ValueError('Credentials already exist; refusing to reinitialize WordPress')
    for key in ('DANK_WP_DB_PASSWORD', 'DANK_WP_DB_ROOT_PASSWORD'):
        if not env.get(key) or env[key].startswith('replace-'):
            raise ValueError('Generate independent test WordPress database credentials first')
    compose = ['docker', 'compose', '-p', 'dank-store-test', '--env-file', str(environment/'.env'),
               '-f', str(ROOT/'docker/docker-compose.dank-wordpress.yml')]
    subprocess.run(compose+['up', '-d', 'dank-wordpress'], check=True)

    def wp(*args, required=True):
        result = subprocess.run(compose+['run', '--rm', '--no-deps', 'dank-wordpress-cli', '--url=https://shop-test.danks.store', *args],
                                capture_output=True, text=True)
        if required and result.returncode:
            # Do not print commands containing credentials or plugin notices.
            raise RuntimeError('WordPress CLI operation failed; inspect the test containers privately')
        return result

    # Wait for the web entrypoint to install core files/configuration.
    for _ in range(60):
        if wp('core', 'version', required=False).returncode == 0:
            break
        time.sleep(2)
    else:
        raise RuntimeError('WordPress files did not initialize')
    if wp('core', 'is-installed', required=False).returncode == 0:
        raise ValueError('Existing WordPress installation; refusing to modify its users')
    username = 'commerce_test_admin'
    password = secrets.token_urlsafe(36)
    wp('core', 'install', '--url=https://shop-test.danks.store', '--title=Dank Mushrooms Test',
       '--admin_user='+username, '--admin_password='+password,
       '--admin_email=staging@example.invalid', '--skip-email')
    # Persist credentials immediately, including if subsequent plugin setup fails.
    credentials.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with credentials.open('x') as stream:
        json.dump({'username':username, 'password':password}, stream)
    credentials.chmod(0o600)
    wp('option', 'update', 'blog_public', '0')
    wp('rewrite', 'structure', '/%postname%/')
    wp('plugin', 'install', 'woocommerce', '--activate')
    app_password = wp('user', 'application-password', 'create', username, 'commerce-staging-sync', '--porcelain').stdout.strip()
    data = json.loads(credentials.read_text()); data['application_password'] = app_password
    credentials.write_text(json.dumps(data)); credentials.chmod(0o600)
    wp('plugin', 'list', '--format=json')  # Confirm CLI can read the resulting installation.
    print('Fresh test WooCommerce installed. Credentials saved privately; no payment gateway configured.')


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('environment', type=Path)
    bootstrap(p.parse_args().environment)
