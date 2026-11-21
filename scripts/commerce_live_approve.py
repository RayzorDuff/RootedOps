"""Update only the existing live-order scope from the ERP backend container."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import tempfile

SITE_CONFIG = Path('/home/frappe/frappe-bench/sites/erp.danks.store/site_config.json')


def apply(scope, action, order_id=None, charge_id=None):
    if scope.get('enabled') is not True or not scope.get('not_before_gmt'):
        raise ValueError('Enable and verify the existing pilot first')
    scope = dict(scope)
    if action == 'review':
        if scope.get('mode', 'pilot') == 'review':
            return scope
        pilot = str(scope['woo_order_id'])
        scope['approved_orders'] = {pilot: {
            'enabled': True, 'capture_enabled': scope.get('capture_enabled') is True,
            'clover_charge_id': scope.get('clover_charge_id')}}
        scope['mode'] = 'review'
        return scope
    if scope.get('mode') != 'review':
        raise ValueError('Switch ERP to review mode after pilot acceptance')
    if not order_id or not re.fullmatch(r'[1-9][0-9]{0,18}', order_id) or int(order_id) >= 2**63:
        raise ValueError('Exact numeric Woo order ID required')
    approvals = dict(scope['approved_orders'])
    approval = dict(approvals.get(order_id) or {})
    if action == 'admit':
        approval['enabled'] = True
    elif action == 'capture':
        if approval.get('enabled') is not True or not charge_id:
            raise ValueError('Approve the order and supply the verified charge first')
        if approval.get('clover_charge_id') not in (None, charge_id):
            raise ValueError('Charge approval already exists and differs; review before proceeding')
        approval.update(capture_enabled=True, clover_charge_id=charge_id)
    approvals[order_id] = approval
    scope['approved_orders'] = approvals
    return scope


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=('review', 'admit', 'capture', 'same-installation', 'storefront-domain'))
    p.add_argument('--order-id')
    p.add_argument('--charge-id')
    args = p.parse_args()
    lock = SITE_CONFIG.with_name('commerce-live-order.lock')
    with lock.open('a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        original = SITE_CONFIG.read_text()
        config = json.loads(original)
        if args.action in ('same-installation', 'storefront-domain'):
            customer = config['commerce_customer_sync']
            if (customer.get('enabled') is not True or customer.get('production_erp_pilot') is not True
                    or customer.get('woo_site') not in ('shop-test.danks.store', 'danks.store', 'dankmushrooms.net')):
                raise ValueError('Verify the existing shared-Linode customer sync first')
            if args.action == 'storefront-domain':
                backup = SITE_CONFIG.with_name('site_config.before-dankmushrooms-net.json')
                if not backup.exists():
                    descriptor = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                    with os.fdopen(descriptor, 'w') as saved:
                        saved.write(original)
                        saved.flush()
                        os.fsync(saved.fileno())
            customer['same_woo_installation'] = True
            if args.action == 'storefront-domain':
                customer['woo_origin'] = 'https://dankmushrooms.net'
        else:
            config['commerce_live_order'] = apply(config['commerce_live_order'], args.action,
                                                 args.order_id, args.charge_id)
        with tempfile.NamedTemporaryFile(mode='w', dir=SITE_CONFIG.parent, delete=False) as output:
            json.dump(config, output, indent=2)
            output.write('\n')
            output.flush()
            os.fsync(output.fileno())
        os.replace(output.name, SITE_CONFIG)
    print(f'ERP {args.action} applied' + (f' for Woo order {args.order_id}' if args.order_id else ''))


if __name__ == '__main__':
    main()
