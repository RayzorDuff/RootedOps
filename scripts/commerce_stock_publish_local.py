"""Publish reviewed MP stock through the same-host Woo inventory implementation.

No order intake, accounting, dispatch, or external payment requests. Run from the
trusted Docker host with private config/worker files and a private state folder.
"""
import argparse
import base64
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

PHP = r'''<?php
$input = json_decode(base64_decode('__INPUT__'), true, 512, JSON_THROW_ON_ERROR);
require 'wp-load.php';
wp_set_current_user(1);
if (untrailingslashit(get_option('home')) !== 'https://dankmushrooms.net'
    || !current_user_can('manage_woocommerce')
    || !function_exists('rootedops_mp_enabled') || !rootedops_mp_enabled()
    || !defined('ROOTEDOPS_MP_WOO_CUTOFF') || ROOTEDOPS_MP_WOO_CUTOFF !== $input['cutoff']) {
    throw new RuntimeException('Reviewed Woo stock configuration required');
}
$request = new WP_REST_Request('POST', '/rootedops/v1/inventory');
$request->set_header('Content-Type', 'application/json');
$request->set_body(wp_json_encode($input['snapshot']));
$result = rootedops_mp_stock($request);
if (($result['status'] ?? '') !== 'published'
    || $result['count'] !== count($input['snapshot']['products'])) {
    throw new RuntimeException('Woo publication was not confirmed');
}
$readback = array();
foreach ($input['snapshot']['products'] as $row) {
    $p = wc_get_product($row['woo_id']);
    $q = $p->get_stock_quantity();
    if (!is_numeric($q) || (float)$q !== (float)(int)$q || $q < 0 || $q > $row['available']) {
        throw new RuntimeException('Invalid Woo stock readback');
    }
    $readback[] = array('woo_id' => $p->get_id(), 'sku' => $p->get_sku(),
        'quantity' => (int)$q, 'mp_available' => $row['available']);
}
echo wp_json_encode(array('publication' => $result, 'products' => $readback)), PHP_EOL;
'''


def reviewed_config(config):
    from datetime import datetime, timezone
    if (config.get('mode') != 'review' or config.get('woo_origin') != 'https://dankmushrooms.net'
            or config.get('mp_database') != 'mushroomprocess_bridge'):
        raise ValueError('Exact installed Woo/MP review configuration required')
    mappings = config.get('published_inventory')
    if not isinstance(mappings, list) or len(mappings) != 24:
        raise ValueError('Reviewed 24-product inventory cohort required')
    if {m['ecommerce_id'] for m in mappings} != set(range(62, 86)):
        raise ValueError('Inventory cohort differs from reviewed owner handoff')
    if len({m['woo_id'] for m in mappings}) != 24:
        raise ValueError('Duplicate Woo stock target')
    cutoff = int(datetime.strptime(config['not_before_gmt'], '%Y-%m-%dT%H:%M:%S')
                 .replace(tzinfo=timezone.utc).timestamp())
    return cutoff, mappings


def publish(config, worker, state, *, run=subprocess.run):
    import psycopg
    from psycopg.conninfo import conninfo_to_dict
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'integrations/commerce'))
    from mp_publication import inventory_snapshot
    cutoff, mappings = reviewed_config(config)
    dsn = worker['COMMERCE_LIVE_MP_DSN']
    if conninfo_to_dict(dsn).get('dbname') != 'mushroomprocess_bridge':
        raise ValueError('Unexpected MP database')

    def connect():
        return psycopg.connect(dsn, options='-c jit=off -c statement_timeout=30000 -c lock_timeout=10000')

    snapshot = inventory_snapshot(SimpleNamespace(connect=connect), mappings, 'danks.store')
    (state / 'last-snapshot.json').write_text(json.dumps(snapshot, indent=2) + '\n')
    encoded = base64.b64encode(json.dumps(dict(cutoff=cutoff, snapshot=snapshot)).encode()).decode()
    result = run(['docker', 'exec', '-i', '-w', '/var/www/html',
                  'dank-store-test-dank-wordpress-1', 'php'],
                 input=PHP.replace('__INPUT__', encoded), text=True, capture_output=True)
    if result.returncode:
        # Configuration/identity errors only; never log connection strings or private environment.
        (state / 'last-error.log').write_text(result.stderr)
        raise RuntimeError('Woo publication failed; private last-error.log retained')
    receipt = json.loads(result.stdout)
    if receipt.get('publication', {}).get('status') != 'published' or len(receipt.get('products', [])) != 24:
        raise ValueError('Woo publication receipt differs')
    (state / 'last-readback.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--worker-env', required=True, type=Path)
    parser.add_argument('--state-dir', required=True, type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    for path in (args.config, args.worker_env):
        if path.stat().st_mode & 0o077:
            raise ValueError('Private configuration files required')
    args.state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    if args.state_dir.stat().st_mode & 0o077:
        raise ValueError('Private publisher state directory required')
    with (args.state_dir / 'publisher.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('Stock publication already running')
            return
        receipt = publish(json.loads(args.config.read_text()), json.loads(args.worker_env.read_text()), args.state_dir)
        print(json.dumps(receipt))


if __name__ == '__main__':
    main()
