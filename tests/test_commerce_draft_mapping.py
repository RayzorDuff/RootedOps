import json
import unittest

from test_commerce_order_pilot import fixture, SITE
from orders import normalize_order, woo_source, OrderReview
from draft_mapping import compile_draft


class DraftMapping(unittest.TestCase):
    def event(self, registered=False, tax='0.00'):
        order = fixture()
        order.update(customer_id=42 if registered else 0, total=str(14 + float(tax)),
                     prices_include_tax=False, date_created_gmt='2026-11-15T21:00:00',
                     discount_total='1.00', shipping_total='3.00', total_tax=tax, cart_tax=tax,
                     shipping_lines=[dict(total='3.00', total_tax='0.00')])
        order['line_items'][0].update(total='11.00', total_tax=tax)
        source, identity = woo_source(json.dumps(order).encode(), SITE, 'synthetic')
        return normalize_order(source, identity, mappings={'1': dict(sku='NATIVE-WOO-SYN',
             ecommerce_id=1, erp_item_code='ITEM')}, gateways={'': 'manual_unpaid'},
             pilot_items={'ITEM'}, reviewed_mapping=True)

    def test_maps_discount_shipping_and_guest_or_registered(self):
        policy = dict(company='Fixture', currency='USD', selling_price_list='USD',
                      shipping_item='SHIP', guest_customer='Guest', allow_zero_tax_fixture=True)
        for registered in (False, True):
            draft, quote = compile_draft(self.event(registered), policy)
            self.assertEqual([row['rate'] for row in draft['items']], ['11.00', '3.00'])
            self.assertEqual(draft.get('customer'), None if registered else 'Guest')
            self.assertIsNone(quote)
        with self.assertRaisesRegex(OrderReview, 'tax_review'):
            compile_draft(self.event(tax='0.50'), policy)

    def test_destination_and_amount_match_quote(self):
        event = self.event(tax='0.50')
        policy = dict(company='Fixture', currency='USD', selling_price_list='USD',
                      shipping_item='SHIP', guest_customer='Guest')
        quote = dict(source_order='10', location_ref='wrong', tax_total='0.50',
                     components=[dict(account_head='TAX', tax_amount='0.50')])
        policy['tax_quotes'] = {'10': quote}
        with self.assertRaisesRegex(OrderReview, 'tax_review'):
            compile_draft(event, policy)
        quote['location_ref'] = event['commercial']['destination']
        draft, _ = compile_draft(event, policy)
        self.assertEqual(draft['taxes'][0]['tax_amount'], '0.50')
