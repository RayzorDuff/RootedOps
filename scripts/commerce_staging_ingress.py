#!/usr/bin/env python3
"""Refresh API-only staging NGINX from an inspected internal WordPress container."""
import argparse
import ipaddress
import json
from pathlib import Path
import subprocess

HOSTS=('erp-test.danks.store','appsmith-test.danks.store','n8n-test.danks.store','shop-test.danks.store')
TARGET=Path('/etc/nginx/sites-available/commerce-staging-closed.conf')


def backend_address(container, network, expected_image):
    labels=container['Config']['Labels']
    if labels.get('com.docker.compose.project')!='dank-store-test' or labels.get('com.docker.compose.service')!='dank-wordpress':
        raise ValueError('Wrong Compose application identity')
    if not container['State']['Running'] or container['Image']!=expected_image:
        raise ValueError('Running reviewed WordPress image required')
    nets=container['NetworkSettings']['Networks']
    if list(nets)!=['dank-store-test_default'] or network['Internal'] is not True:
        raise ValueError('Sole internal Dank network required')
    if network['Id']!=nets['dank-store-test_default']['NetworkID']:
        raise ValueError('Network identity drift')
    address=ipaddress.ip_address(nets['dank-store-test_default']['IPAddress'])
    if address.version!=4 or not address.is_private or address.is_loopback or address.is_unspecified:
        raise ValueError('Private container IPv4 required')
    return str(address)


def render(address):
    # Revalidate even when called independently of Docker inspection.
    ip=ipaddress.ip_address(address)
    if ip.version!=4 or not ip.is_private or ip.is_loopback or ip.is_unspecified:
        raise ValueError('Private IPv4 required')
    lines=['# Managed by commerce_staging_ingress.py; API-only test access.',
           'server {',' listen 80;',' server_name '+' '.join(HOSTS)+';',
           ' location ^~ /.well-known/acme-challenge/ { root /var/www/rootedops-acme; }',
           ' location / { return 403; }','}',
           'server {',' listen 443 ssl;',' server_name '+' '.join(HOSTS)+';',
           ' client_max_body_size 64m;',
           ' ssl_certificate /etc/letsencrypt/live/commerce-staging/fullchain.pem;',
           ' ssl_certificate_key /etc/letsencrypt/live/commerce-staging/privkey.pem;',
           ' ssl_protocols TLSv1.2 TLSv1.3;']
    for route in ('^~ /wp-json/wc/v3/','= /wp-json/wp/v2/media'):
        lines+=[' location '+route+' {','  if ($host != shop-test.danks.store) { return 403; }',
                '  if ($http_authorization = "") { return 401; }',
                '  proxy_pass http://'+str(ip)+':80;','  proxy_set_header Host $host;',
                '  proxy_set_header X-Forwarded-Proto https;',
                '  proxy_set_header Authorization $http_authorization;',' }']
    return '\n'.join(lines+[' location / { return 403; }','}',''])


def refresh(environment, apply=False):
    p=environment.resolve()
    if (p/'TEST_ENVIRONMENT').read_text().strip()!='rootedops-full-test':raise ValueError('Test marker required')
    installed=json.loads((p/'private/wordpress-offline-receipt.json').read_text())
    if installed['controls']!={'cron_disabled':True,'http_blocked':True,'mail_blocked':True,'payment_gateways':0}:
        raise ValueError('Reviewed isolated installation required')
    tls=json.loads((p/'tls-acceptance.json').read_text())
    if tls.get('tls_verified') is not True or set(tls['domains'])!=set(HOSTS):raise ValueError('Verified test TLS receipt required')
    image=json.loads((p/'shop-input-receipt.json').read_text())['images']['wordpress:7.1.4-php8.3-apache']['id']
    container=json.loads(subprocess.check_output(['docker','inspect','dank-store-test-dank-wordpress-1'],text=True))[0]
    network=json.loads(subprocess.check_output(['docker','network','inspect','dank-store-test_default'],text=True))[0]
    address=backend_address(container,network,image);text=render(address)
    if not apply:
        print('Reviewed backend and API-only configuration validated; use --apply to refresh NGINX.');return
    if not TARGET.is_file() or not Path('/etc/letsencrypt/live/commerce-staging/fullchain.pem').is_file():
        raise ValueError('Existing closed staging vhost and issued certificate required')
    previous=TARGET.read_text()
    for host in HOSTS:
        if host not in previous:raise ValueError('Unexpected installed vhost; inspect manually')
    backup=p/'nginx-staging.previous.conf';backup.write_text(previous);backup.chmod(0o600)
    try:
        TARGET.write_text(text)
        subprocess.run(['nginx','-t'],check=True)
        subprocess.run(['systemctl','reload','nginx'],check=True)
    except Exception:
        TARGET.write_text(previous)
        subprocess.run(['nginx','-t'],check=True)
        subprocess.run(['systemctl','reload','nginx'],check=True)
        raise RuntimeError('Ingress refresh failed; prior configuration restored') from None
    receipt=p/'shop-upstream-receipt.json'
    receipt.write_text(json.dumps({'container_id':container['Id'],'network_internal':True,'address':address,'port':80,
        'refresh_required_after_container_recreation':True,'routes':['/wp-json/wc/v3/','/wp-json/wp/v2/media'],'all_other_paths':403},indent=2));receipt.chmod(0o600)
    print('Validated API-only staging ingress refreshed; application egress unchanged.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('environment',type=Path);p.add_argument('--apply',action='store_true')
    a=p.parse_args();refresh(a.environment,a.apply)
