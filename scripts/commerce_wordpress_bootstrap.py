#!/usr/bin/env python3
"""Install a fresh, private-credential WooCommerce test shop. No merchant setup."""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]


def bootstrap(environment, resume=False):
    from commerce_restore import read_env
    environment = environment.resolve()
    env = read_env(environment/'.env')
    if env.get('ERPNEXT_SITE_NAME') != 'erp-test.danks.store':
        raise ValueError('Only the authorized commerce test environment is supported')
    credentials = environment/'private/wordpress-credentials.json'
    if credentials.exists() and not resume:
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
    installed = wp('core', 'is-installed', required=False).returncode == 0
    username = 'commerce_test_admin'
    if installed:
        if not resume or not credentials.exists():
            raise ValueError('Existing unowned WordPress installation; refusing to modify its users')
        data=json.loads(credentials.read_text())
        if data.get('username')!=username:
            raise ValueError('Unexpected test owner')
        wp('user', 'get', username, '--field=ID')
    else:
        password = secrets.token_urlsafe(36)
        wp('core', 'install', '--url=https://shop-test.danks.store', '--title=Dank Mushrooms Test',
           '--admin_user='+username, '--admin_password='+password,
           '--admin_email=staging@example.invalid', '--skip-email')
        credentials.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd=os.open(credentials,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as stream:
            json.dump({'username':username, 'password':password}, stream)
    # Reviewed pins from WordPress.org release archive and WooCommerce directory.
    # https://wordpress.org/download/releases/ ; https://wordpress.org/plugins/woocommerce/
    if wp('core', 'version').stdout.strip()!='7.1.4':
        wp('core', 'update', '--version=7.1.4')
        wp('core', 'update-db')
    wp('option', 'update', 'blog_public', '0')
    wp('rewrite', 'structure', '/%postname%/')
    wp('plugin', 'install', 'woocommerce', '--version=11.2.1', '--activate')
    data = json.loads(credentials.read_text())
    if not data.get('application_password'):
        data['application_password'] = wp('user', 'application-password', 'create', username, 'commerce-staging-sync', '--porcelain').stdout.strip()
    credentials.write_text(json.dumps(data)); credentials.chmod(0o600)
    wp('plugin', 'list', '--format=json')  # Confirm CLI can read the resulting installation.
    print('Fresh test WooCommerce installed. Credentials saved privately; no payment gateway configured.')


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('environment', type=Path)
    p.add_argument('--resume',action='store_true',help='Resume only an owned test installation with its private credentials')
    a=p.parse_args();bootstrap(a.environment,a.resume)
