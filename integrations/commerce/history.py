"""Operational Customer / draft Sales Order conversion, with no financial replay.

Uses complete API-shaped orders; CSV orders lacking stable line/customer IDs or
currency remain archived until explicit identity/enrichment review. Never match
customers solely by email. Source identities are scoped to provider AND store.
"""
import hashlib
import json
from decimal import Decimal
from reviewed_catalog import money


def identity(provider, site, kind, external_id):
    parts = [str(x).strip() for x in (provider, site, kind, external_id)]
    if not all(parts):
        raise ValueError('Complete source identity required')
    return hashlib.sha256(json.dumps(parts, separators=(',', ':')).encode()).hexdigest()


def convert_history(data, review):
    from ecwid_migrate import digest
    if review['source_sha256'] != digest(data):
        raise ValueError('History review does not match source')
    site = str(data['store_id'])
    customers, orders, seen = [], [], set()
    customer_map = {}
    for source in data.get('customers', []):
        key = identity('ecwid', site, 'customer', source['id'])
        if key in seen:
            raise ValueError('Duplicate customer identity')
        seen.add(key)
        customer_map[str(source['id'])] = key
        customer = {'customer_name': source.get('name') or source.get('email') or 'Ecwid customer ' + str(source['id']),
                    'customer_type': 'Individual', 'customer_group': review['customer_group'],
                    'territory': review['territory']}
        record={'source_key':key,'source_payload':source,'customer':customer}
        enrichment=review.get('customers',{}).get(str(source['id']),{})
        if enrichment:
            contact=enrichment.get('contact')
            if contact:
                if set(contact)-{'first_name','last_name','email_ids','phone_nos'} or not contact.get('first_name'):
                    raise ValueError('Reviewed Contact fields/name required')
                record['contact']=contact
            addresses=enrichment.get('addresses',[])
            ids=set()
            for address in addresses:
                if not address.get('source_address_id') or address['source_address_id'] in ids:
                    raise ValueError('Stable unique reviewed address identity required')
                ids.add(address['source_address_id'])
                if set(address)-{'source_address_id','address_title','address_type','address_line1','address_line2','city','state','pincode','country','email_id','phone'}:
                    raise ValueError('Unsupported Address fields')
                if address.get('address_type') not in ('Billing','Shipping') or not all(address.get(k) for k in ['address_line1','city','country']):
                    raise ValueError('Complete reviewed billing/shipping address required')
            record['addresses']=addresses
        customers.append(record)
    for source in data.get('orders', []):
        key = identity('ecwid', site, 'order', source['id'])
        if key in seen:
            raise ValueError('Duplicate order identity')
        seen.add(key)
        customer_key = customer_map[str(source['customerId'])]
        currency = source['currency']
        if currency != review['currency']:
            raise ValueError('Historical order currency mismatch')
        lines, line_ids = [], set()
        net = Decimal('0')
        for line in source['items']:
            line_id = str(line['id'])
            if line_id in line_ids:
                raise ValueError('Duplicate source line identity')
            line_ids.add(line_id)
            qty = Decimal(str(line['quantity']))
            if not qty.is_finite() or qty <= 0:
                raise ValueError('Invalid historical quantity')
            # Explicit per-line final net total avoids guessing discount allocation.
            approved = review['orders'][str(source['id'])]['lines'][line_id]
            line_total = Decimal(money(approved['net_total']))
            item_code = review['items'][str(line['sku'])]
            lines.append({'item_code': item_code, 'qty': str(qty),
                          'rate': format(line_total / qty, 'f'), 'delivery_date': review['delivery_date']})
            net += line_total
        if not lines:
            raise ValueError('Empty historical order')
        charges = review['orders'][str(source['id'])]['charges']
        tax_rows = []
        for charge in charges:
            amount = Decimal(money(charge['amount']))
            tax_rows.append({'charge_type': 'Actual', 'account_head': charge['erp_account'],
                             'description': charge['description'], 'tax_amount': str(amount)})
            net += amount
        if net != Decimal(money(source['total'])):
            raise ValueError('Historical total mismatch; reconcile discount/shipping/tax first')
        order = {'company': review['company'], 'currency': currency, 'conversion_rate': review['conversion_rate'],
                 'transaction_date': source['createDate'][:10], 'delivery_date': review['delivery_date'],
                 'selling_price_list': review['selling_price_list'], 'items': lines, 'taxes': tax_rows,
                 'ignore_pricing_rule': 1, 'docstatus': 0,
                 'remarks': 'Historical Ecwid import; audit only. Do not submit or fulfill. Source ' + key}
        orders.append({'source_key': key, 'customer_key': customer_key, 'source_payload': source,
                       'expected_total': money(source['total']), 'sales_order': order})
    return {'schema_version': 1, 'customers': customers, 'orders': orders,
            'financial_replay': False, 'fulfillment_replay': False}
