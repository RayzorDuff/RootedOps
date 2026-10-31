#!/usr/bin/env python3
"""Fresh isolated Dank shop from rendered recovery configuration and a verified ZIP."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import time
import zipfile
import yaml
from commerce_restore import read_env

WP_VERSION = '7.1.4'
WOO_VERSION = '11.2.1'
ISOLATION = """<?php
/* Isolated staging only: no email, external HTTP or payment gateways. */
add_filter('pre_wp_mail', '__return_true');
add_filter('pre_http_request', function () { return new WP_Error('staging_egress_blocked', 'External HTTP disabled in staging'); }, 10, 3);
add_filter('woocommerce_available_payment_gateways', '__return_empty_array', 999);
"""


def inspect(environment, archive, digest):
    if (environment/'TEST_ENVIRONMENT').read_text().strip() != 'rootedops-full-test':
        raise ValueError('Rendered full-test marker required')
    config = yaml.safe_load((environment/'dank.yml').read_text())
    if config.get('name') != 'dank-store-test' or not config['networks']['default'].get('internal'):
        raise ValueError('Dedicated internal Dank test project required')
    if set(config['services']) != {'dank-wordpress','dank-wordpress-db','dank-wordpress-cli'}:
        raise ValueError('Only dedicated Dank services are supported')
    if any(config.get('volumes',{}).values()):
        raise ValueError('Shared/external volumes forbidden')
    for service in config['services'].values():
        if service.get('network_mode') or service.get('networks'):
            raise ValueError('Unexpected network override')
        if any(not str(p).startswith('127.0.0.1:') for p in service.get('ports', [])):
            raise ValueError('Loopback-only publication required')
    if config['services']['dank-wordpress']['image'] != 'wordpress:'+WP_VERSION+'-php8.3-apache':
        raise ValueError('Review the pinned WordPress image before installation')
    env = read_env(environment/'.env')
    if env.get('ERPNEXT_SITE_NAME') != 'erp-test.danks.store':
        raise ValueError('Authorized -test staging hostname required')
    for key in ('DANK_WP_DB_PASSWORD', 'DANK_WP_DB_ROOT_PASSWORD'):
        if len(env.get(key, '')) < 24 or env[key].startswith('replace-'):
            raise ValueError('Independent generated test credentials required')
    if env['DANK_WP_DB_PASSWORD'] == env['DANK_WP_DB_ROOT_PASSWORD']:
        raise ValueError('Distinct database credentials required')
    if not archive.is_file() or hashlib.sha256(archive.read_bytes()).hexdigest() != digest:
        raise ValueError('WooCommerce archive SHA256 mismatch')
    with zipfile.ZipFile(archive) as z:
        for name in z.namelist():
            p = Path(name)
            if p.is_absolute() or '..' in p.parts or p.parts[0] != 'woocommerce':
                raise ValueError('Unsafe WooCommerce ZIP path')
        header = z.read('woocommerce/woocommerce.php').decode()
        if not any(line.strip().lstrip('*').strip() == 'Version: '+WOO_VERSION for line in header.splitlines()):
            raise ValueError('Wrong WooCommerce archive version')
    return config


def private_json(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as f:
        json.dump(value, f, indent=2)


def bootstrap(environment, archive, digest):
    environment, archive = environment.resolve(), archive.resolve()
    config = inspect(environment, archive, digest)
    private = environment/'private'
    private.mkdir(mode=0o700, exist_ok=True)
    receipt = private/'wordpress-offline-receipt.json'
    credentials = private/'wordpress-credentials.json'
    if receipt.exists() or credentials.exists():
        raise ValueError('Existing installation evidence; inspect state instead of reinstalling')
    base = ['docker', 'compose', '--env-file', str(environment/'.env'), '-f', str(environment/'dank.yml')]
    if subprocess.check_output(base+['ps', '-aq'], text=True).strip() or subprocess.check_output(
        ['docker','volume','ls','-q','--filter','label=com.docker.compose.project=dank-store-test'], text=True).strip():
        raise ValueError('Fresh empty Dank project required; restored ERP/MP projects are retained')
    mu = environment/'wordpress-isolation'
    mu.mkdir(mode=0o755, exist_ok=True)
    (mu/'rootedops-staging.php').write_text(ISOLATION)
    (mu/'rootedops-staging.php').chmod(0o644)
    extra = config['services']['dank-wordpress'].get('environment', {}).get('WORDPRESS_CONFIG_EXTRA', '')
    extra += "\ndefine('DISABLE_WP_CRON', true);\ndefine('WP_HTTP_BLOCK_EXTERNAL', true);\ndefine('AUTOMATIC_UPDATER_DISABLED', true);\n"
    services = {}
    for name in ('dank-wordpress', 'dank-wordpress-cli'):
        services[name] = {'environment': {'WORDPRESS_CONFIG_EXTRA': extra}, 'volumes': [str(mu)+':/var/www/html/wp-content/mu-plugins:ro']}
    services['dank-wordpress-cli']['volumes'].append(str(archive)+':/opt/woocommerce.zip:ro')
    override = private/'wordpress-offline.yml'
    override.write_text(yaml.safe_dump({'services': services}, sort_keys=False)); override.chmod(0o600)
    compose = base+['-f', str(override)]
    subprocess.run(compose+['config', '--quiet'], check=True, stdin=subprocess.DEVNULL)
    # Record credentials before mutations so a failure cannot silently create a second owner.
    data = {'username': 'commerce_test_admin', 'password': secrets.token_urlsafe(36)}
    private_json(credentials, data)
    def wp(*args, required=True):
        a = subprocess.run(compose+['run','--rm','--no-deps','dank-wordpress-cli',*args],
                           stdin=subprocess.DEVNULL, capture_output=True, text=True)
        if required and a.returncode:
            raise RuntimeError('Private WordPress operation failed; inspect isolated project; do not reinstall')
        return a
    try:
        subprocess.run(compose+['up','-d','dank-wordpress'],check=True,stdin=subprocess.DEVNULL)
        for _ in range(60):
            if wp('core','version',required=False).returncode == 0:
                break
            time.sleep(2)
        else:
            raise RuntimeError('WordPress files did not initialize')
        if wp('core','is-installed',required=False).returncode == 0:
            raise ValueError('Unexpected existing installation')
        if wp('core','version').stdout.strip() != WP_VERSION:
            raise ValueError('Unexpected WordPress core version')
        wp('core','install','--url=https://shop-test.danks.store','--title=Dank Mushrooms Test',
           '--admin_user='+data['username'],'--admin_password='+data['password'],
           '--admin_email=staging@example.invalid','--skip-email')
        wp('option','update','blog_public','0')
        wp('plugin','install','/opt/woocommerce.zip','--activate')
        wp('option','update','woocommerce_allow_tracking','no')
        wp('rewrite','structure','/%postname%/')
        version=wp('plugin','get','woocommerce','--field=version').stdout.strip()
        if version != WOO_VERSION:
            raise ValueError('Installed WooCommerce version mismatch')
        probe=wp('eval',"echo json_encode(['cron_disabled'=>DISABLE_WP_CRON,'http_blocked'=>WP_HTTP_BLOCK_EXTERNAL,'mail_blocked'=>has_filter('pre_wp_mail','__return_true')!==false,'payment_gateways'=>count(WC()->payment_gateways()->get_available_payment_gateways())]);").stdout
        controls=json.loads(probe)
        if not all(controls[k] is True for k in ('cron_disabled','http_blocked','mail_blocked')) or controls['payment_gateways'] != 0:
            raise ValueError('Isolation controls did not activate')
        private_json(receipt, {'wordpress':WP_VERSION,'woocommerce':version,'archive_sha256':digest,'controls':controls,'scope':'Fresh synthetic shop; no Rooted Psyche restore or merchant setup'})
        print('Isolated WooCommerce initialized; credentials and receipt saved privately; no gateway enabled.')
    except Exception:
        subprocess.run(compose+['stop','dank-wordpress'],stdin=subprocess.DEVNULL,capture_output=True)
        raise


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('environment',type=Path);p.add_argument('archive',type=Path);p.add_argument('--sha256',required=True)
    a=p.parse_args();bootstrap(a.environment,a.archive,a.sha256)
