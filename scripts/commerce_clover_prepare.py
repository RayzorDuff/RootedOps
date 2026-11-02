#!/usr/bin/env python3
"""Prepare official Clover 2.3.2 on isolated test2, disabled with no credentials."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import urllib.request
import zipfile

from commerce_catalog_batch import guarded_environment
from ecwid_migrate import private_write

URL = 'https://downloads.wordpress.org/plugin/clover-payments-for-woocommerce.2.3.2.zip'
SHA = 'c0c58e50c905b5bcbfa55b72c0aa178a6fb5b9eb2cebd9b013f6c7618754e4f5'
CONTAINER = 'dank-store-test-dank-wordpress-1'
SLUG = 'clover-payments-for-woocommerce'


def run(environment):
    _, private = guarded_environment(environment)
    work = private / 'clover-readiness'; work.mkdir(mode=0o700, exist_ok=True)
    archive = work / (SLUG + '.2.3.2.zip')
    if not archive.exists():
        archive.write_bytes(urllib.request.urlopen(URL, timeout=20).read())
    if hashlib.sha256(archive.read_bytes()).hexdigest() != SHA:
        raise ValueError('Official archive drift; review before installation')
    target = '/var/www/html/wp-content/plugins/' + SLUG
    exists = subprocess.run(['docker', 'exec', CONTAINER, 'test', '-d', target]).returncode == 0
    if not exists:
        with tempfile.TemporaryDirectory() as tmp:
            with zipfile.ZipFile(archive) as z:
                for name in z.namelist():
                    if not name.startswith(SLUG + '/') or '..' in Path(name).parts:
                        raise ValueError('Unexpected archive path')
                z.extractall(tmp)
            subprocess.run(['docker', 'cp', str(Path(tmp) / SLUG), CONTAINER + ':' + target], check=True)
    # All keys must remain absent. Refuse to overwrite a configured merchant.
    php = r'''require '/var/www/html/wp-load.php';
require_once ABSPATH.'wp-admin/includes/plugin.php';
$key='woocommerce_clover_payments_settings';$settings=get_option($key,[]);
foreach($settings as $k=>$v){if(preg_match('/key|merchant_id/',$k)&&!empty($v)){throw new Exception('Configured credentials require separate review');}}
$settings=array_merge($settings,['enabled'=>'no','environment'=>'sandbox','apple_pay'=>'no','debug_mode'=>'no']);
update_option($key,$settings);
$plugin='clover-payments-for-woocommerce/clover-payments-for-woocommerce.php';
$data=get_plugin_data(WP_PLUGIN_DIR.'/'.$plugin,false,false);
if($data['Version']!=='2.3.2'){throw new Exception('Installed version drift');}
$error=activate_plugin($plugin,'',false,true);if(is_wp_error($error)){throw new Exception('Activation failed');}
echo json_encode(['plugin'=>$plugin,'version'=>$data['Version'],'active'=>is_plugin_active($plugin),'enabled'=>$settings['enabled'],'environment'=>$settings['environment'],'credentials_present'=>false]);'''
    result = json.loads(subprocess.check_output(['docker', 'exec', CONTAINER, 'php', '-r', php]))
    # New process proves normal bootstrap and registration, not a card checkout.
    probe = r'''require '/var/www/html/wp-load.php';$all=WC()->payment_gateways()->payment_gateways();
if(!isset($all['clover_payments'])){throw new Exception('Clover gateway not registered');}
$g=$all['clover_payments'];if($g->enabled!=='no'||$g->get_option('environment')!=='sandbox'||$g->is_available()){throw new Exception('Clover isolation drift');}
echo json_encode(['gateway_registered'=>true,'available'=>false,'wordpress'=>get_bloginfo('version'),'woocommerce'=>WC_VERSION,'php'=>PHP_VERSION]);'''
    result.update(json.loads(subprocess.check_output(['docker', 'exec', CONTAINER, 'php', '-r', probe])))
    guarded_environment(environment)
    result.update(archive_sha256=SHA, sandbox_checkout_tested=False, merchant_entitlement_confirmed=False)
    private_write(work / 'prepared.json', result)
    print(json.dumps(result))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('environment', type=Path)
    run(parser.parse_args().environment)
