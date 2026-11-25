#!/usr/bin/env python3
"""Preview/apply source-faithful Woo history and ERP draft Sales Orders.

Operator-only Docker access; no processor calls, submissions or MP writes.
The source file and private receipts stay on the production host, outside Git.
"""
import argparse
from collections import Counter
from datetime import datetime
from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
CENT = Decimal('0.01')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def money(value, label='source monetary amount'):
    number = Decimal(str(value))
    if not number.is_finite():
        raise ValueError('Invalid ' + label)
    rounded = number.quantize(CENT, rounding=ROUND_HALF_UP)
    # Ecwid JSON numbers can carry binary arithmetic residue, including a tiny
    # negative zero. This tolerance is one millionth of a cent, not permission
    # to round a genuine fractional-cent price/discount into a different amount.
    if rounded < 0 or abs(number - rounded) > Decimal('0.00000001'):
        raise ValueError('Invalid ' + label + ': ' + str(value))
    return rounded if rounded else Decimal('0.00')


def allocate(amount, weights):
    """Deterministic cent allocation; never infer a tax rate or change order tax."""
    cents = int(money(amount) * 100)
    weights = [money(value) for value in weights]
    total = sum(weights)
    if not total:
        if cents:
            raise ValueError('Cannot allocate an amount over zero merchandise')
        return ['0.00'] * len(weights)
    exact = [Decimal(cents) * weight / total for weight in weights]
    units = [int(value.to_integral_value(rounding=ROUND_FLOOR)) for value in exact]
    rank = sorted(range(len(units)), key=lambda i: (-(exact[i] - units[i]), i))
    for index in rank[:cents - sum(units)]:
        units[index] += 1
    return [format(Decimal(value) / 100, '.2f') for value in units]


def compile_orders(source, woo, erp):
    if str(source['store_id']) != '95802503':
        raise ValueError('Unexpected Ecwid store')
    users = {row['email'].strip().lower(): row['id'] for row in woo['users']}
    users_by_id = {str(row['id']): row for row in woo['users']}
    products = {str(row['id']): row for row in woo['products']}
    by_source, by_sku = {}, {}
    for row in products.values():
        if row['source']:
            if row['source'] in by_source:
                raise ValueError('Duplicate Woo source product identity')
            by_source[row['source']] = row
        if row['sku']:
            if row['sku'] in by_sku:
                raise ValueError('Duplicate Woo product SKU')
            by_sku[row['sku']] = row
    plans, seen = [], set()
    for raw in sorted(source['orders'], key=lambda row: str(row['id'])):
        oid = str(raw['id'])
        if oid in seen:
            raise ValueError('Duplicate Ecwid order')
        seen.add(oid)
        # Import recorded sales, not unpaid/unfulfilled checkout attempts. An
        # unpaid delivered order is retained: fulfillment is independent proof.
        if (raw.get('paymentStatus') not in ('PAID', 'REFUNDED')
                and raw.get('fulfillmentStatus') not in ('SHIPPED', 'DELIVERED')):
            continue
        email = str(raw.get('email') or '').strip().lower()
        woo_id = users.get(email, 0)
        customers = set(erp['email_customers'].get(email, [])) if email else set()
        if woo_id and str(woo_id) in erp['woo_customers']:
            customers.add(erp['woo_customers'][str(woo_id)])
        if len(customers) > 1:
            raise ValueError('Ambiguous existing ERP customer for order ' + oid)
        customer = next(iter(customers), 'Dank Mushrooms Web Guest')
        if email and customer == 'Dank Mushrooms Web Guest':
            raise ValueError('Unresolved named purchaser on order ' + oid)
        if not woo_id and customer in erp['customer_woo']:
            candidate = erp['customer_woo'][customer]
            if candidate not in users_by_id:
                raise ValueError('ERP points to missing Woo account')
            woo_id = int(candidate)
        # Woo supports named guest orders. Keep the exact existing ERP Customer
        # and original billing identity without creating a duplicate login.
        if raw.get('pricesIncludeTax'):
            raise ValueError('Tax-inclusive source order requires explicit mapping: ' + oid)
        total, tax, subtotal = [money(raw[key], oid + ' ' + key) for key in ('total', 'tax', 'subtotal')]
        shipping = money((raw.get('shippingOption') or {}).get('shippingRate', 0))
        discount = money(raw.get('discount', 0), oid + ' discount') + money(raw.get('couponDiscount', 0), oid + ' couponDiscount')
        if total != subtotal + shipping + tax - discount or discount > subtotal:
            raise ValueError('Source order components do not balance: ' + oid)
        if raw.get('usdTotal') is not None and money(raw['usdTotal']) != total:
            raise ValueError('Source currency needs review: ' + oid)
        lines, line_ids = [], set()
        for line in raw['items']:
            lid = str(line['id'])
            qty = Decimal(str(line['quantity']))
            if lid in line_ids or not qty.is_finite() or qty <= 0:
                raise ValueError('Invalid source line identity/quantity')
            line_ids.add(lid)
            unit = money(line.get('priceWithoutTax', line['price']))
            gross = unit * qty
            if gross != gross.quantize(CENT):
                raise ValueError('Source line amount needs review')
            sku = str(line.get('sku') or '')
            product = by_source.get('ecwid:' + str(source['store_id']) + ':product:' + str(line.get('productId')))
            if product is None:
                product = by_sku.get(sku)
            candidates = [product['sku']] if product else []
            candidates.append(sku)
            item = next((code for code in candidates if code and erp['items'].get(code)), None)
            fallback = 'ECWID-HIST-' + str(line.get('productId') or hashlib.sha256(sku.encode()).hexdigest()[:16])
            lines.append(dict(id=lid, name=line.get('name') or sku or 'Historical item', sku=sku,
                              source_product_id=line.get('productId'), quantity=str(qty),
                              gross=format(gross, '.2f'), original_tax=line.get('tax'),
                              woo_product_id=product['id'] if product else 0,
                              erp_item=item or fallback, create_item=item is None))
        if not lines or sum(money(line['gross']) for line in lines) != subtotal:
            raise ValueError('Source merchandise subtotal differs from lines: ' + oid)
        reductions = allocate(discount, [line['gross'] for line in lines])
        net = [money(line['gross']) - money(reduction) for line, reduction in zip(lines, reductions)]
        tax_parts = allocate(tax, net)
        for line, amount, tax_part in zip(lines, net, tax_parts):
            line.update(net=format(amount, '.2f'), tax=tax_part,
                        rate=format(amount / Decimal(line['quantity']), 'f'))
        payment, fulfillment = raw['paymentStatus'], raw['fulfillmentStatus']
        if payment == 'REFUNDED':
            status = 'refunded'
        elif payment == 'PAID':
            status = 'completed' if fulfillment in ('DELIVERED', 'SHIPPED') else 'processing'
        elif payment == 'AWAITING_PAYMENT':
            status = 'on-hold'
        else:
            raise ValueError('Unreviewed source payment status: ' + oid)
        created = datetime.strptime(raw['createDate'], '%Y-%m-%d %H:%M:%S %z').isoformat()
        source_key = 'ecwid:' + str(source['store_id']) + ':order:' + oid
        erp_key = hashlib.sha256(json.dumps(['ecwid', str(source['store_id']), 'order', oid], separators=(',', ':')).encode()).hexdigest()
        plans.append(dict(id=oid, source_key=source_key, erp_key=erp_key, currency='USD', created=created,
                          woo_customer_id=woo_id, erp_customer=customer, status=status,
                          source_payment=payment, source_fulfillment=fulfillment,
                          payment_method=raw.get('paymentMethod'), total=str(total), tax=str(tax),
                          subtotal=str(subtotal), shipping=str(shipping), discount=str(discount),
                          reported_refund=str(money(raw.get('refundedAmount', 0))),
                          person=raw.get('shippingPerson') or {}, email=email, lines=lines))
    return plans


def remote(kind, value, receipts):
    filename = 'commerce_history_woo.php' if kind == 'woo' else 'commerce_history_erp.py'
    code = (ROOT / 'scripts' / filename).read_text()
    if kind == 'woo':
        import base64
        encoded = base64.b64encode(json.dumps(value).encode()).decode()
        code = "<?php\n$input=json_decode(base64_decode('" + encoded + "'),true);\n" + code.removeprefix('<?php')
        command = ['sudo', 'docker', 'exec', '-i', '-w', '/var/www/html',
                   'dank-store-test-dank-wordpress-1', 'php']
        body = code
    else:
        command = ['sudo', 'docker', 'exec', '-i', '-w', '/home/frappe/frappe-bench/sites',
                   'erpnext-backend', '/home/frappe/frappe-bench/env/bin/python', '-c', code]
        body = json.dumps(value)
    result = subprocess.run(command, input=body, text=True, capture_output=True)
    if result.returncode:
        (receipts / (kind + '-error.log')).write_text(result.stdout + '\n' + result.stderr)
        raise RuntimeError(kind + ' operation failed; inspect private ' + str(receipts / (kind + '-error.log')))
    return json.loads(result.stdout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['preview', 'rehearse', 'apply'])
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--receipts', type=Path, required=True)
    parser.add_argument('--review-sha')
    args = parser.parse_args()
    os.umask(0o077)
    args.receipts.mkdir(mode=0o700, parents=True, exist_ok=True)
    if args.receipts.stat().st_mode & 0o077 or args.source.stat().st_mode & 0o077:
        raise ValueError('Source and receipt directory must be private')
    source = json.loads(args.source.read_text())
    if not source.get('orders'):
        raise ValueError('No source orders')
    woo = remote('woo', {'action': 'snapshot'}, args.receipts)
    erp = remote('erp', {'action': 'snapshot'}, args.receipts)
    plans = compile_orders(source, woo, erp)
    packet = dict(schema_version=1, source_sha=digest(source), orders=plans)
    review_sha = digest(packet)
    summary = dict(orders=len(plans), total=str(sum(money(p['total']) for p in plans)),
                   excluded_unpaid_unfulfilled_orders=sorted(str(row['id']) for row in source['orders']
                       if str(row['id']) not in {plan['id'] for plan in plans}),
                   woo_guest_order_ids=[plan['id'] for plan in plans if not plan['woo_customer_id']],
                   source_statuses=dict(Counter(p['source_payment'] + '/' + p['source_fulfillment'] for p in plans)),
                   historical_item_codes=sorted({line['erp_item'] for p in plans for line in p['lines'] if line['create_item']}),
                   review_sha=review_sha, erp_documents='draft Sales Orders; no submitted invoices or payments')
    if args.action == 'preview':
        (args.receipts / 'review.json').write_text(json.dumps(packet, indent=2) + '\n')
        (args.receipts / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    else:
        reviewed = json.loads((args.receipts / 'review.json').read_text())
        if not args.review_sha or args.review_sha != review_sha or digest(reviewed) != review_sha:
            raise ValueError('Exact preview hash and unchanged source/mapping review required')
        rehearsal = args.action == 'rehearse'
        # Each destination is idempotent. A retry reuses committed records if the other destination failed.
        erp_result = remote('erp', {'action': 'apply', 'orders': plans, 'dry_run': rehearsal}, args.receipts)
        (args.receipts / ('erp-rehearsal.json' if rehearsal else 'erp-result.json')).write_text(json.dumps(erp_result, indent=2) + '\n')
        if rehearsal:
            summary.update(erp_drafts_validated=len(erp_result), erp_changes='rolled back', woo_changes='none')
        else:
            woo_result = remote('woo', {'action': 'apply', 'orders': plans}, args.receipts)
            (args.receipts / 'woo-result.json').write_text(json.dumps(woo_result, indent=2) + '\n')
            summary.update(erp=erp_result, woo=woo_result)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
