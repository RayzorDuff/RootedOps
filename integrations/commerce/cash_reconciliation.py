"""Project separately recorded MP cash receipts into reviewed ERP accounting."""
import argparse
from datetime import datetime
from decimal import Decimal
import hashlib
import hmac
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
import uuid

from customer_signals import request_erp_customer
from mp_publication import woo_request


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def packet(receipt, approval):
    if approval.get('enabled') is not True:
        raise ValueError('Cash receipt requires explicit review approval')
    source = '|'.join(receipt[k] for k in ('provider', 'site_key', 'external_order_id'))
    if approval.get('source_key') != source:
        raise ValueError('Cash source identity differs from approval')
    snapshot = receipt['snapshot']
    raw = snapshot.get('items')
    lines = []
    reviewed = approval['lines']
    if raw is not None:
        if len(raw) != len(reviewed):
            raise ValueError('Cash sale lines require exact reviewed mappings')
        for index, item in enumerate(raw):
            line = reviewed[index]
            if (str(item.get('id', index + 1)) != line['line_id'] or item.get('sku') != line['source_sku']
                    or str(item.get('productId')) != line['external_product_id']
                    or type(item.get('quantity')) is not int or item['quantity'] != line['quantity']):
                raise ValueError('Cash product, SKU, line or quantity differs from mapping')
            lines.append({k: line[k] for k in ('line_id', 'erp_item_code', 'quantity')})
    else:
        lines = snapshot['lines']
        if lines != reviewed:
            raise ValueError('Woo cash mappings differ from reserved lines')
    if not lines or any(not line['erp_item_code'] or type(line['quantity']) is not int or line['quantity'] <= 0 for line in lines):
        raise ValueError('Mapped cash sale requires positive integer quantities')
    fingerprint = hashlib.sha256(canonical(snapshot)).hexdigest()
    if approval.get('source_fingerprint') != fingerprint:
        raise ValueError('Cash snapshot needs renewed review')
    return dict(provider=receipt['provider'], site_key=receipt['site_key'], external_order_id=receipt['external_order_id'],
                receipt_id=str(receipt['receipt_id']), amount=f"{Decimal(str(receipt['amount'])):.2f}",
                currency=receipt['currency'], received_at=receipt['received_at'].isoformat(), operator=receipt['operator'],
                source_fingerprint=fingerprint, lines=lines, processor='cash', state='received',
                verification='mp_operator_receipt', refunded_amount='0.00', commercial=snapshot.get('commercial'))


def check_current_source(connect, receipt):
    with connect() as db:
        if receipt['provider'] == 'ecwid':
            rows = db.execute("""SELECT status,payment_status,jsonb_build_object(
                'items',coalesce(nullif(items_json,''),'[]')::jsonb,'subtotal',subtotal,
                'tax',tax_total,'total',order_total,'currency',currency),payment_processor,processor_payment_id,clover_payment_id
                FROM public.ecommerce_orders WHERE coalesce(nullif(provider,''),'ecwid')=%s
                AND coalesce(nullif(site_key,''),'dank_mushrooms')=%s
                AND coalesce(nullif(external_order_id,''),ecwid_order_id)=%s""",
                tuple(receipt[k] for k in ('provider','site_key','external_order_id'))).fetchall()
            if len(rows) != 1 or str(rows[0][0]).upper() in ('WILL_NOT_DELIVER','CANCELLED','RETURNED') or str(rows[0][1]).upper() in ('CANCELLED','CANCELED','REFUNDED','FAILED'):
                raise ValueError('Cash source missing, ambiguous, cancelled or refunded: review')
            if rows[0][3] != 'cash' or rows[0][4] or rows[0][5]:
                raise ValueError('Cash tender was replaced or processor evidence appeared: review')
            current = rows[0][2]
        else:
            rows = db.execute("""SELECT status,snapshot FROM public.mp_commerce_orders
                WHERE provider=%s AND site_key=%s AND external_order_id=%s""",
                tuple(receipt[k] for k in ('provider','site_key','external_order_id'))).fetchall()
            if len(rows) != 1 or rows[0][0] not in ('pending','on-hold','processing','completed') or rows[0][1].get('refunds') or rows[0][1].get('payment_processor') != 'cash':
                raise ValueError('Cash source cancelled, refunded or tender changed: review')
            snapshot = rows[0][1]
            current = {k:snapshot.get(k) for k in ('lines','commercial','external_customer_id','total','currency')}
            current['total'] = Decimal(str(current['total']))
    expected = dict(receipt['snapshot'])
    if receipt['provider'] == 'woocommerce':
        expected['total'] = Decimal(str(expected['total']))
    if current != expected:
        raise ValueError('Cash source commercial details changed: review')


def reconcile(connect, receipt_id, config, request=request_erp_customer, woo=woo_request):
    origin = config['erp_origin']
    if origin not in ('https://erp.danks.store', 'https://erp-test.danks.store', 'https://erp-test2.danks.store'):
        raise ValueError('Reviewed ERP destination required')
    if config.get('enabled') is not True or origin == 'https://erp.danks.store' and config.get('production') is not True:
        raise ValueError('Cash ERP posting is disabled')
    receipt_id = str(uuid.UUID(receipt_id))
    with connect() as db:
        row = db.execute('SELECT provider,site_key,external_order_id,amount,currency,received_at,operator,snapshot FROM public.mp_commerce_cash_receipts WHERE receipt_id=%s', (receipt_id,)).fetchone()
    if row is None:
        raise ValueError('Durable MP cash receipt required')
    receipt = dict(zip(('provider', 'site_key', 'external_order_id', 'amount', 'currency', 'received_at', 'operator', 'snapshot'), row), receipt_id=receipt_id)
    check_current_source(connect, receipt)
    data = packet(receipt, config['approved_receipts'].get(receipt_id) or {})
    secret = os.environ['COMMERCE_CASH_EVIDENCE_KEY']
    if len(secret) < 32:
        raise ValueError('Private cash evidence key required')
    proof = hmac.digest(secret.encode(), canonical(data), 'sha256').hex()
    result = request(origin + '/api/method/rootedops_commerce.cash_payment.reconcile_receipt',
                     os.environ['ERP_AUTHORIZATION'], 'POST', dict(payload=json.dumps(data), signature=proof))['message']
    references = dict(result, erp_site=urlsplit(origin).hostname)
    with connect() as db:
        db.execute('SELECT public.mp_commerce_ack_cash(%s,%s::jsonb)', (receipt_id, json.dumps(references)))
    # ERP is committed first. A failed Woo/MP step retries the same cash UUID.
    if receipt['provider'] == 'woocommerce':
        woo(config['woo_origin'], os.environ['WOO_MP_AUTHORIZATION'], 'POST',
            '/orders/' + receipt['external_order_id'] + '/cash-receipt',
            {k: data[k] for k in ('receipt_id', 'amount', 'currency')})
        try:
            with connect() as db:
                db.execute('SELECT public.mp_commerce_confirm_cash(%s)', (receipt_id,))
        except Exception:
            return dict(status='awaiting_paid_woo_snapshot_or_review', receipt_id=receipt_id, **references)
    return dict(status='accounted', receipt_id=receipt_id, **references)


def load(path):
    path = Path(path)
    if path.stat().st_mode & 0o077:
        raise ValueError('Cash configuration must be private (chmod 600)')
    config = json.loads(path.read_text())
    from production_order import connector
    return config, connector(os.environ['COMMERCE_LIVE_MP_DSN'], config['mp_database'])


def cycle(path):
    config, connect = load(path)
    if config.get('enabled') is not True:
        return [{'status': 'disabled'}]
    outcomes = []
    for receipt, approval in sorted(config.get('approved_receipts', {}).items()):
        if approval.get('enabled') is not True:
            continue
        try:
            outcomes.append(reconcile(connect, receipt, config))
        except Exception:
            # Do not print private responses or customer/order payloads.
            outcomes.append(dict(receipt_id=receipt, status='accounting_review'))
    return outcomes


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=('list', 'preview', 'post', 'cycle'))
    p.add_argument('--config', type=Path, required=True)
    p.add_argument('--receipt-id')
    args = p.parse_args()
    config, connect = load(args.config)
    if args.command == 'cycle':
        result = cycle(args.config)
    elif args.command == 'list':
        with connect() as db:
            rows = db.execute('SELECT receipt_id,provider,site_key,external_order_id,amount,currency,erp_references IS NOT NULL FROM public.mp_commerce_cash_receipts ORDER BY received_at DESC LIMIT 100').fetchall()
        result = [dict(zip(('receipt_id','provider','site_key','order_id','amount','currency','erp_acknowledged'), row)) for row in rows]
    else:
        ident = str(uuid.UUID(args.receipt_id))
        if args.command == 'post':
            result = reconcile(connect, ident, config)
        else:
            with connect() as db:
                row = db.execute('SELECT provider,site_key,external_order_id,amount,currency,snapshot FROM public.mp_commerce_cash_receipts WHERE receipt_id=%s', (ident,)).fetchone()
            if not row:
                raise ValueError('Receipt not found')
            result = dict(zip(('provider','site_key','order_id','amount','currency'), row[:5]), receipt_id=ident,
                          source_fingerprint=hashlib.sha256(canonical(row[5])).hexdigest(),
                          source_lines=[{k:item.get(k) for k in ('id','sku','productId','quantity','price')} for item in row[5].get('items',[])] if 'items' in row[5] else row[5].get('lines'),
                          commercial=row[5].get('commercial'))
    print(json.dumps(result, default=str))


if __name__ == '__main__':
    main()
