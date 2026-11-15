#!/usr/bin/env python3
"""Build a private review CSV from Ecwid customer and order CSVs. Reads only."""
import argparse
from collections import defaultdict
import csv
from datetime import datetime
import json
import os
from pathlib import Path
import tempfile

from ecwid_csv import read_rows
from ecwid_migrate import api, digest, pages, private_write
from history import convert_history

ADDRESS_FIELDS = ('name', 'street_1', 'street_2', 'city', 'state_code', 'postal_code',
                  'country_code', 'phone')
REVIEW_FIELDS = ('ecwid_store_id', 'ecwid_customer_id', 'erp_customer', 'erp_contact',
                 'erp_billing_address', 'erp_shipping_address', 'woo_site', 'woo_customer_id',
                 'approved_contact_order', 'decision')


def key(value):
    return value.strip().casefold()


def review(customers_path, orders_path, *, store_id='', source_customers=()):
    customers = read_rows(customers_path, {'email', 'name', 'registered', 'accept marketing'})
    lines = read_rows(orders_path, {'order_number', 'email', 'timestamp', 'fulfillment_status_code',
        'payment_status_code'} | {prefix + field for prefix in ('shipto_person_', 'bill_person_')
                                  for field in ADDRESS_FIELDS})
    orders = defaultdict(list)
    by_email = defaultdict(list)
    for row in lines:
        if not row['order_number'].strip():
            raise ValueError('Missing order number')
        orders[row['order_number'].strip()].append(row)
    ambiguous_order_count = 0
    for number, rows in orders.items():
        emails = {key(row['email']) for row in rows if row['email'].strip()}
        if len(emails) > 1:
            ambiguous_order_count += 1
            continue
        if emails:
            for email in emails:
                by_email[email].extend(rows)

    stable_ids = defaultdict(set)
    for row in source_customers:
        if row.get('email') and str(row.get('id', '')).isdigit():
            stable_ids[key(row['email'])].add(str(row['id']))

    customer_rows = defaultdict(list)
    for row in customers:
        customer_rows[key(row['email'])].append(row)
    review_rows = []
    for email, profiles in sorted(customer_rows.items()):
        profile = profiles[0]
        order_records = {}
        for order in by_email.get(email, []):
            shipping = {field: order['shipto_person_' + field].strip() for field in ADDRESS_FIELDS}
            billing = {field: order['bill_person_' + field].strip() for field in ADDRESS_FIELDS}
            evidence = {k: order[k] for k in ('order_number','timestamp','fulfillment_status_code','payment_status_code')}
            evidence.update(shipping=shipping, billing=billing)
            order_records[json.dumps(evidence, sort_keys=True)] = evidence
        candidates = sorted(order_records.values(),
            key=lambda r: datetime.strptime(r['timestamp'], '%b %d, %Y %I:%M %p'), reverse=True)
        # Coalesce repeated line rows, but preserve each different historic contact or address.
        addresses = {tuple(r['shipping'][f] for f in ADDRESS_FIELDS[1:-1])
                     for r in candidates if r['shipping']['street_1']}
        phones = {r['shipping']['phone'] for r in candidates if r['shipping']['phone']}
        ids = stable_ids[email]
        row = dict.fromkeys(REVIEW_FIELDS, '')
        row.update(ecwid_store_id=store_id, email=email, export_name=profile['name'],
                   customer_export_rows=len(profiles), registered=profile['registered'],
                   export_marketing_consent=profile['accept marketing'],
                   order_numbers=len({r['order_number'] for r in candidates}),
                   shipping_address_variants=len(addresses), shipping_phone_variants=len(phones),
                   order_contact_candidates=json.dumps(candidates, ensure_ascii=False))
        row['review_flags'] = '|'.join(flag for flag, show in (
            ('missing_email', not email), ('duplicate_customer_email', len(profiles) != 1),
            ('unresolved_ecwid_id', len(ids) != 1), ('multiple_shipping_addresses', len(addresses) > 1),
            ('multiple_shipping_phones', len(phones) > 1), ('missing_export_name', not profile['name']),
        ) if show)
        # An email match against the API is still an initial identity candidate.
        row['ecwid_id_candidate'] = next(iter(ids)) if len(ids) == 1 else ''
        review_rows.append(row)
    summary = dict(customer_export_rows=len(customers), review_rows=len(review_rows),
                   order_line_rows=len(lines), unique_orders=len(orders),
                   orders_without_email=sum(not any(r['email'].strip() for r in rows) for rows in orders.values()),
                   orders_with_ambiguous_email=ambiguous_order_count,
                   order_only_emails=len(set(by_email) - set(customer_rows)),
                   shipping_address_candidates=sum(bool(r['shipping_address_variants']) for r in review_rows),
                   shipping_phone_candidates=sum(bool(r['shipping_phone_variants']) for r in review_rows))
    return review_rows, summary


def write_csv(path, rows):
    if not rows:
        raise ValueError('No customer export rows')
    # Spreadsheet clients interpret leading formula characters, even in CSV.
    def cell(value):
        if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')):
            return "'" + value
        return value
    path = Path(path)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='', dir=path.parent, delete=False) as out:
        writer = csv.DictWriter(out, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows({k: cell(v) for k, v in row.items()} for row in rows)
    os.replace(out.name, path)


def compile_new_customers(review_path, *, store_id, customer_group, territory):
    """Turn rows marked create_erp into the existing customer-only history plan."""
    with Path(review_path).open(encoding='utf-8-sig', newline='') as stream:
        reviewed = list(csv.DictReader(stream))
    data = {'store_id': store_id, 'customers': [], 'orders': []}
    details = {}
    for row in reviewed:
        if row['decision'] != 'create_erp':
            continue
        source_id = row['ecwid_customer_id']
        if (row['ecwid_store_id'] != store_id or not source_id.isascii() or not source_id.isdecimal()
                or row['customer_export_rows'] != '1' or source_id in details
                or row['erp_customer'] or row['erp_contact'] or row['erp_billing_address']
                or row['erp_shipping_address']):
            raise ValueError('New ERP import requires a reviewed stable source ID and no existing ERP mapping')
        email, name = row['email'], row['export_name'].strip()
        if not email or not name:
            raise ValueError('Enter a reviewed name and email for each new ERP customer')
        parts = name.split(None, 1)
        contact = dict(first_name=parts[0], last_name=parts[1] if len(parts) == 2 else '',
                       email_ids=[dict(email_id=email, is_primary=1)])
        addresses = []
        if row['approved_contact_order']:
            matches = [r for r in json.loads(row['order_contact_candidates'])
                       if r['order_number'] == row['approved_contact_order']]
            if len(matches) != 1:
                raise ValueError('Approved order must identify exactly one contact snapshot')
            shipping = matches[0]['shipping']
            country = {'US': 'United States', 'CA': 'Canada'}.get(shipping['country_code'])
            if not country or not shipping['street_1'] or not shipping['city']:
                raise ValueError('Review unsupported or incomplete shipping address manually')
            addresses.append(dict(source_address_id='account-shipping', address_title=name, address_type='Shipping',
                address_line1=shipping['street_1'], address_line2=shipping['street_2'], city=shipping['city'],
                state=shipping['state_code'], pincode=shipping['postal_code'], country=country))
            if shipping['phone']:
                contact['phone_nos'] = [dict(phone=shipping['phone'], is_primary_phone=1)]
        data['customers'].append(dict(id=source_id, name=name, email=email))
        details[source_id] = dict(contact=contact, addresses=addresses)
    plan = convert_history(data, dict(source_sha256=digest(data), customer_group=customer_group,
                                      territory=territory, customers=details))
    plan['reject_existing_email'] = True
    return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compile-reviewed')
    parser.add_argument('--customer-group')
    parser.add_argument('--territory')
    parser.add_argument('--customers')
    parser.add_argument('--orders')
    parser.add_argument('--output', required=True)
    parser.add_argument('--store-id', default='')
    parser.add_argument('--recover-ecwid-ids', action='store_true')
    args = parser.parse_args()
    if args.compile_reviewed:
        if not args.store_id or not args.customer_group or not args.territory:
            parser.error('--compile-reviewed requires --store-id, --customer-group, and --territory')
        plan = compile_new_customers(args.compile_reviewed, store_id=args.store_id,
                                     customer_group=args.customer_group, territory=args.territory)
        private_write(args.output, plan)
        print(json.dumps({'approved_new_customers': len(plan['customers']), 'orders': 0}))
        return
    if not args.customers or not args.orders:
        parser.error('--customers and --orders are required for review')
    source = ()
    if args.recover_ecwid_ids:
        if not args.store_id.isascii() or not args.store_id.isdecimal():
            parser.error('--recover-ecwid-ids requires a numeric --store-id')
        root = 'https://app.ecwid.com/api/v3/' + args.store_id + '/'
        token = 'Bearer ' + os.environ['ECWID_TOKEN']
        source = pages(lambda path: api(root + path, token), 'customers')
    rows, summary = review(args.customers, args.orders, store_id=args.store_id, source_customers=source)
    write_csv(args.output, rows)
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
