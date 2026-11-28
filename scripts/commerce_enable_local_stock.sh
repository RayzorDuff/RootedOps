#!/usr/bin/env bash
# Activate same-host stock publication and prepare HTTP redirects; keep checkout restricted.
set -euo pipefail
umask 077
sudo -v
source_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
site_root="$HOME/RootedOps"
work="$HOME/commerce-migration/public-opening-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -m 700 -p "$work"
export COMMERCE_STOCK_SETUP="$work" COMMERCE_SITE_REPO="$site_root"
printf 'Private activation receipts: %s\n' "$work"
cd "$site_root"
dc=(sudo docker compose --env-file .env -f docker/docker-compose.dank-wordpress.yml -p dank-store-test)
"${dc[@]}" exec -T dank-wordpress-db sh -ec \
  'exec mariadb-dump -u root -p"$MARIADB_ROOT_PASSWORD" --single-transaction --routines --triggers "$MARIADB_DATABASE"' > "$work/wordpress.sql"
test -s "$work/wordpress.sql"
python3 - <<'PY'
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess

work=Path(os.environ['COMMERCE_STOCK_SETUP'])
root=Path(os.environ['COMMERCE_SITE_REPO'])
config=json.loads((Path.home()/'commerce-migration/woo-order-pilot/orders.json').read_text())
if len(config.get('published_inventory',[])) != 24 or config.get('woo_origin') != 'https://dankmushrooms.net':
    raise SystemExit('STOP: expected reviewed 24-product configuration.')
cutoff=str(int(datetime.strptime(config['not_before_gmt'],'%Y-%m-%dT%H:%M:%S').replace(tzinfo=timezone.utc).timestamp()))
info=json.loads(subprocess.check_output(['sudo','docker','inspect','dank-store-test-dank-wordpress-1'],text=True))[0]
env=dict(row.split('=',1) for row in info['Config']['Env'])
(work/'wordpress-runtime.before.json').write_text(json.dumps(info,indent=2))
extra=env.get('WORDPRESS_CONFIG_EXTRA','')
if not extra:
    raise SystemExit('STOP: expected current environment-driven WordPress configuration.')
if 'ROOTEDOPS_MP_WOO_ENABLED' not in extra:
    extra+="\nif (!defined('ROOTEDOPS_MP_WOO_ENABLED')) define('ROOTEDOPS_MP_WOO_ENABLED', getenv('DANK_MP_WOO_ENABLED') === '1');\n"
if 'ROOTEDOPS_MP_WOO_CUTOFF' not in extra:
    extra+="\nif (!defined('ROOTEDOPS_MP_WOO_CUTOFF') && ctype_digit(getenv('DANK_MP_WOO_CUTOFF') ?: '')) define('ROOTEDOPS_MP_WOO_CUTOFF', (int)getenv('DANK_MP_WOO_CUTOFF'));\n"
env.update(DANK_MP_WOO_ENABLED='1',DANK_MP_WOO_CUTOFF=cutoff,WORDPRESS_CONFIG_EXTRA=extra)
# Persist the reviewed flags for normal future Compose deployment too.
env_path=root/'.env'
old=env_path.read_text()
(work/'compose.env.before').write_text(old)
updates={'DANK_MP_WOO_ENABLED':'1','DANK_MP_WOO_CUTOFF':cutoff,
         'DANK_WP_CUSTOMER_WEBHOOK_ENABLED':env.get('DANK_WP_CUSTOMER_WEBHOOK_ENABLED','0')}
new=old
for key,value in updates.items():
    pattern=r'(?m)^(?:export\s+)?'+re.escape(key)+r'=.*$'
    if re.search(pattern,new):new=re.sub(pattern,key+'='+value,new)
    else:new=new.rstrip('\n')+'\n'+key+'='+value+'\n'
tmp=env_path.with_name('.env.stock-pending')
with tmp.open('x') as handle:handle.write(new)
tmp.chmod(env_path.stat().st_mode & 0o777)
tmp.replace(env_path)
# Snapshot every live environment value, escape Compose dollar interpolation,
# and pin the exact image ID. Recreate only this WordPress service, never ERP/DB.
override={'services':{'dank-wordpress':{'image':info['Image'],
    'environment':{k:v.replace('$','$$') for k,v in env.items()}}}}
(work/'wordpress-runtime.json').write_text(json.dumps(override,indent=2))
print('Prepared preserved WordPress environment and persistent MP stock flags.')
PY
"${dc[@]}" -f "$work/wordpress-runtime.json" config --quiet
"${dc[@]}" -f "$work/wordpress-runtime.json" up -d --no-deps --force-recreate --pull never dank-wordpress
sudo docker exec -i -w /var/www/html dank-store-test-dank-wordpress-1 php <<'PHP'
<?php
require 'wp-load.php';
if (!function_exists('rootedops_mp_enabled') || !rootedops_mp_enabled()
    || !defined('ROOTEDOPS_MP_WOO_CUTOFF') || !is_int(ROOTEDOPS_MP_WOO_CUTOFF)
    || !function_exists('rootedops_cutover_checkout_guard')
    || untrailingslashit(get_option('home')) !== 'https://dankmushrooms.net') {
    throw new RuntimeException('Stock flags, hostname or checkout restriction not verified');
}
echo wp_json_encode(array('mp_enabled'=>true,'cutoff'=>ROOTEDOPS_MP_WOO_CUTOFF,
    'stored_home'=>get_option('home'),'stored_siteurl'=>get_option('siteurl'),
    'checkout_restricted'=>true)), PHP_EOL;
PHP
pilot="$HOME/commerce-migration/woo-order-pilot"
state="$pilot/stock-publication-state"
mkdir -m 700 -p "$state"
cat > "$work/dank-woo-stock.service" <<UNIT
[Unit]
Description=Dank Woo stock-only publication from MushroomProcess
After=docker.service network-online.target
Requires=docker.service
[Service]
Type=oneshot
User=root
WorkingDirectory=$source_root
UMask=0077
Environment=PYTHONDONTWRITEBYTECODE=1
ExecStart=$HOME/commerce-migration/customer-pilot/venv/bin/python $source_root/scripts/commerce_stock_publish_local.py --config $pilot/orders.json --worker-env $pilot/worker-environment.json --state-dir $state
TimeoutStartSec=180
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=$state
UNIT
cat > "$work/dank-woo-stock.timer" <<'UNIT'
[Unit]
Description=Publish reviewed Dank Woo inventory every minute
[Timer]
OnActiveSec=15s
OnUnitActiveSec=60s
AccuracySec=5s
Unit=dank-woo-stock.service
[Install]
WantedBy=timers.target
UNIT
if sudo test -e /etc/systemd/system/dank-woo-stock.service; then
  sudo grep -q '^Description=Dank Woo stock-only publication from MushroomProcess$' /etc/systemd/system/dank-woo-stock.service
  sudo cp /etc/systemd/system/dank-woo-stock.service "$work/stock-service.before"
fi
sudo install -m 644 "$work/dank-woo-stock.service" /etc/systemd/system/dank-woo-stock.service
sudo install -m 644 "$work/dank-woo-stock.timer" /etc/systemd/system/dank-woo-stock.timer
sudo systemctl daemon-reload
sudo systemctl start dank-woo-stock.service
sudo systemctl start dank-woo-stock.service
sudo cat "$state/last-readback.json"
sudo systemctl enable --now dank-woo-stock.timer
sudo systemctl list-timers dank-woo-stock.timer --no-pager
# Prepare origin routing before the owner edits DNS. No existing storefront
# virtual host is overwritten. Existing subdomain/mail/ERP routing is unchanged.
sudo cp -a /etc/nginx "$work/nginx.before"
python3 - "$source_root" "$work" <<'PY'
import csv
import json
from pathlib import Path
import re
import subprocess
import sys
root,work=map(Path,sys.argv[1:])
target='/etc/nginx/sites-available/danks.store-cutover.conf'
enabled='/etc/nginx/sites-enabled/danks.store-cutover.conf'
if subprocess.run(['sudo','test','-e',target]).returncode == 0 or subprocess.run(['sudo','test','-e',enabled]).returncode == 0:
    raise SystemExit('STOP: danks.store cutover configuration already exists; stock timer remains active.')
current=subprocess.check_output(['sudo','nginx','-T'],text=True,stderr=subprocess.DEVNULL)
for declaration in re.findall(r'\bserver_name\s+([^;]+);',current):
    if set(declaration.split()) & {'danks.store','www.danks.store'}:
        raise SystemExit('STOP: existing danks.store vhost requires review; stock timer remains active.')
rows=list(csv.DictReader((root/'doc/fixtures/dank-ecwid-staging-redirects.csv').open()))
if len(rows)!=42 or len({r['path'] for r in rows})!=42:
    raise SystemExit('STOP: unexpected legacy redirect manifest.')
lines=['# Dank cutover: canonical storefront is dankmushrooms.net', 'server {',
       '    listen 80;', '    server_name danks.store www.danks.store;',
       '    location ^~ /.well-known/acme-challenge/ { root /var/www/letsencrypt; }']
for row in rows:
    path=row['path']
    if not path.startswith('/') or any(c in path for c in '\r\n$"\\'):
        raise SystemExit('STOP: invalid legacy path.')
    if row['disposition']=='redirect':
        dest=row['final_path']
        if not dest.startswith('/') or dest.startswith('//') or any(c in dest for c in '\r\n$"\\'):
            raise SystemExit('STOP: invalid redirect target.')
        action='return 302 https://dankmushrooms.net'+dest+'$is_args$args;'
    elif row['disposition'] in ('retired','decision'):action='return 404;'
    else:raise SystemExit('STOP: unknown legacy disposition.')
    lines.append('    location = '+json.dumps(path)+' { '+action+' }')
lines += ['    location / { return 302 https://dankmushrooms.net$request_uri; }','}']
p=work/'danks.store-cutover.conf';p.write_text('\n'.join(lines)+'\n')
subprocess.run(['sudo','install','-m','644',str(p),target],check=True)
subprocess.run(['sudo','ln','-s',target,enabled],check=True)
check=subprocess.run(['sudo','nginx','-t'])
if check.returncode:
    subprocess.run(['sudo','rm',enabled],check=True)
    raise SystemExit('STOP: new HTTP vhost disabled after validation failure; NGINX not reloaded.')
subprocess.run(['sudo','mkdir','-p','/var/www/letsencrypt/.well-known/acme-challenge'],check=True)
subprocess.run(['sudo','systemctl','reload','nginx'],check=True)
print('Prepared HTTP origin and 42 legacy paths; DNS has not changed.')
PY
curl --silent --show-error --max-time 15 --output /dev/null \
  --write-out 'Origin redirect: HTTP %{http_code} to %{redirect_url}\n' \
  --resolve danks.store:80:127.0.0.1 http://danks.store/products/
printf '\nStock timer is active. Checkout remains restricted. DNS/TLS and public opening are next.\n'
printf 'Private activation receipts: %s\n' "$work"
