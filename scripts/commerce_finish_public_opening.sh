#!/usr/bin/env bash
# Run only after stock activation and the owner has pointed old apex/www DNS here.
set -euo pipefail
umask 077
sudo -v
source_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
work="$HOME/commerce-migration/public-enabled-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -m 700 -p "$work"
python3 - <<'PY'
import socket
for host in ('danks.store','www.danks.store'):
    addresses={r[4][0] for r in socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)}
    if addresses != {'45.33.107.185'}:
        raise SystemExit('STOP: temporary DNS-only apex/www must resolve to the Linode before certificate issuance: '+host+' '+str(sorted(addresses)))
print('Both old frontend hostnames resolve to the Linode.')
PY
sudo systemctl is-active --quiet dank-woo-stock.timer
sudo certbot --nginx --non-interactive --agree-tos --no-redirect \
  --keep-until-expiring --cert-name danks.store \
  -d danks.store -d www.danks.store
sudo nginx -t
python3 - "$source_root" <<'PY'
from concurrent.futures import ThreadPoolExecutor
import csv
from pathlib import Path
import sys
from urllib.request import Request,build_opener,HTTPRedirectHandler
from urllib.error import HTTPError
class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None
def head(url):
    request=Request(url,method='HEAD',headers={'User-Agent':'RootedOps-Commerce/1.0'})
    try:response=build_opener(NoRedirect).open(request,timeout=20)
    except HTTPError as error:response=error
    with response:return response.code,response.headers.get('Location')
def check(row):
    path=row['path']
    status,location=head('https://danks.store'+path)
    if row['disposition']=='redirect':
        expected='https://dankmushrooms.net'+row['final_path']
        if status not in (301,302) or location != expected:
            return path+': wrong old-host status/destination '+str((status,location))
        end,_=head(expected)
        if end!=200:return path+': canonical destination returned '+str(end)
    elif status!=404:return path+': retired/unresolved path must remain 404, got '+str(status)
    return None
rows=list(csv.DictReader((Path(sys.argv[1])/'doc/fixtures/dank-ecwid-staging-redirects.csv').open()))
if len(rows)!=42:raise SystemExit('STOP: unexpected redirect cohort.')
with ThreadPoolExecutor(max_workers=5) as pool:
    failures=[value for value in pool.map(check,rows) if value]
for host in ('danks.store','www.danks.store'):
    result=head('https://'+host+'/?cutover_probe=1')
    if result[0] not in (301,302) or result[1]!='https://dankmushrooms.net/?cutover_probe=1':
        failures.append(host+': root/query redirect differs '+str(result))
if failures:
    print('\n'.join(failures))
    raise SystemExit('STOP: redirect checks failed; checkout restriction retained.')
print('Verified HTTPS, apex/www query preservation, and all 42 legacy paths.')
PY
sudo systemctl start dank-woo-stock.service
test "$(sudo systemctl show dank-woo-stock.service -p Result --value)" = success
sudo cat "$HOME/commerce-migration/woo-order-pilot/stock-publication-state/last-readback.json" > "$work/stock-readback.json"
python3 - "$work/stock-readback.json" <<'PY'
import json
import sys
v=json.load(open(sys.argv[1]))
if v.get('publication',{}).get('status')!='published' or len(v.get('products',[]))!=24:
    raise SystemExit('STOP: current inventory publication not confirmed.')
print('Current 24-product stock publication verified, revision',v['publication']['revision'])
PY
sudo docker exec -i -w /var/www/html dank-store-test-dank-wordpress-1 php <<'PHP'
<?php
require 'wp-load.php';
if (get_option('home') !== 'https://dankmushrooms.net' || get_option('siteurl') !== 'https://dankmushrooms.net'
    || !rootedops_mp_enabled() || !defined('ROOTEDOPS_MP_WOO_CUTOFF')) {
    throw new RuntimeException('Canonical hostname or stock guard is not ready');
}
$merchant=get_option('woocommerce_new_order_settings',array());
if (($merchant['enabled'] ?? '') !== 'yes' || ($merchant['recipient'] ?? '') !== 'sales@edanks.com') {
    throw new RuntimeException('Merchant notification settings differ');
}
foreach (array('customer_processing_order','customer_on_hold_order','customer_completed_order') as $id) {
    $settings=get_option('woocommerce_'.$id.'_settings',array());
    if (($settings['enabled'] ?? '') !== 'yes') throw new RuntimeException('Customer notification disabled');
}
echo "Canonical URL, stock guard and notification settings verified.\n";
PHP
sudo systemctl is-active --quiet dank-woo-order-inbox.service
# Promote only the prepared legacy redirects after every target check passed.
sudo cp /etc/nginx/sites-available/danks.store-cutover.conf "$work/legacy-vhost.before-permanent.conf"
sudo python3 - <<'PY'
from pathlib import Path
p=Path('/etc/nginx/sites-available/danks.store-cutover.conf')
s=p.read_text()
if '# Dank cutover: canonical storefront is dankmushrooms.net' not in s:
    raise SystemExit('STOP: unexpected legacy vhost.')
p.write_text(s.replace('return 302 https://dankmushrooms.net','return 301 https://dankmushrooms.net'))
PY
if ! sudo nginx -t; then
  sudo cp "$work/legacy-vhost.before-permanent.conf" /etc/nginx/sites-available/danks.store-cutover.conf
  exit 1
fi
sudo systemctl reload nginx
plugin=/var/www/html/wp-content/mu-plugins/rootedops-cutover-checkout.php
if sudo docker exec dank-store-test-dank-wordpress-1 test -e "$plugin"; then
  sudo docker cp "dank-store-test-dank-wordpress-1:$plugin" "$work/checkout-guard.before.php"
  sudo docker exec dank-store-test-dank-wordpress-1 rm "$plugin"
fi
sudo docker exec -i -w /var/www/html dank-store-test-dank-wordpress-1 php <<'PHP'
<?php
require 'wp-load.php';
if (function_exists('rootedops_cutover_checkout_guard')) throw new RuntimeException('Checkout restriction still loaded');
echo "Temporary manager-only checkout restriction removed.\n";
PHP
for host in danks.store www.danks.store; do
  curl --fail --silent --show-error --max-time 20 --user-agent 'RootedOps-Commerce/1.0' \
    --output /dev/null --write-out "$host: HTTP %{http_code} redirect=%{redirect_url}\n" "https://$host/"
done
curl --fail --silent --show-error --location --max-redirs 3 --max-time 30 \
  --user-agent 'RootedOps-Commerce/1.0' --output /dev/null \
  --write-out 'Public checkout: HTTP %{http_code} at %{url_effective}\n' https://dankmushrooms.net/checkout/
printf '\nPublic Woo checkout enabled. Stock timer active. ERP order review remains manual.\n'
printf 'Ecwid stays closed and its stock workflow paused. Order 214 remains unshipped.\n'
printf 'Private opening receipts: %s\n' "$work"
