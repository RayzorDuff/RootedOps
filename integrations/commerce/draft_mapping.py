"""Compile an isolated Sales Order draft from reviewed site policy and Woo money."""
from datetime import date
from decimal import Decimal, InvalidOperation

from orders import OrderReview


def cents(value):
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount < 0 or amount != amount.quantize(Decimal('.01')):
            raise ValueError
    except (ValueError, InvalidOperation) as exc:
        raise OrderReview('commercial_review') from exc
    return amount


def compile_draft(event, policy):
    commercial = event['commercial']
    if event['currency'] != policy.get('currency'):
        raise OrderReview('commercial_review')
    if type(commercial['order_date']) is not str:
        raise OrderReview('commercial_review')
    order_date = date.fromisoformat(commercial['order_date']).isoformat()
    items = []
    for line in event['lines']:
        line_total = cents(commercial['line_totals'][line['line_id']])
        rate = line_total / line['quantity']
        if rate != rate.quantize(Decimal('.01')):
            raise OrderReview('commercial_review')
        items.append(dict(item_code=line['erp_item_code'], qty=line['quantity'], rate=str(rate)))
    shipping = cents(commercial['shipping'])
    if shipping:
        item = policy.get('shipping_item')
        if not item or item in {line['item_code'] for line in items}:
            raise OrderReview('commercial_review')
        items.append(dict(item_code=item, qty=1, rate=str(shipping)))
    draft = dict(company=policy['company'], currency=event['currency'], conversion_rate=1,
                 transaction_date=order_date, delivery_date=order_date,
                 selling_price_list=policy['selling_price_list'], items=items, taxes=[],
                 ignore_pricing_rule=1, docstatus=0)
    if event['external_customer_id'] is None:
        draft['customer'] = policy.get('guest_customer')
        if not draft['customer']:
            raise OrderReview('customer_mapping_review')
    quote = policy.get('tax_quotes', {}).get(event['external_order_id'])
    if not quote:
        if cents(commercial['tax']) or policy.get('allow_zero_tax_fixture') is not True:
            raise OrderReview('tax_review')
        return draft, None
    if (quote.get('location_ref') != commercial['destination']
            or quote.get('source_order') != event['external_order_id']
            or cents(quote.get('tax_total')) != cents(commercial['tax'])):
        raise OrderReview('tax_review')
    taxes = {}
    for component in quote['components']:
        account = component['account_head']
        taxes[account] = taxes.get(account, 0) + cents(component['tax_amount'])
    draft['taxes'] = [dict(charge_type='Actual', account_head=account,
                           description='Reviewed destination tax', tax_amount=str(amount))
                      for account, amount in sorted(taxes.items()) if amount]
    return draft, quote
