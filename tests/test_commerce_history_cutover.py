import copy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('history_cutover', Path(__file__).parents[1] / 'scripts/commerce_history_cutover.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class HistoryCutoverTests(unittest.TestCase):
    def setUp(self):
        self.source = dict(store_id='95802503', orders=[dict(id='fixture', email='buyer@example.invalid',
            createDate='2026-01-01 12:00:00 +0000', paymentStatus='PAID', fulfillmentStatus='DELIVERED',
            total='31.81', subtotal='29.90', tax='1.91', discount=0, couponDiscount=0,
            shippingOption=dict(shippingRate=0), items=[dict(id='line', productId=10, sku='old-sku',
            name='Fixture product', quantity=2, price='14.95', priceWithoutTax='14.95', tax=1.92)])])
        self.woo = dict(users=[dict(id=5, email='buyer@example.invalid')], products=[dict(id=34,
            sku='current-sku', source='ecwid:95802503:product:10')])
        self.erp = dict(email_customers={'buyer@example.invalid': ['Existing Buyer']},
            woo_customers={'5': 'Existing Buyer'}, customer_woo={'Existing Buyer': '5'},
            items={'current-sku': True})

    def compile(self):
        return module.compile_orders(self.source, self.woo, self.erp)

    def test_order_level_tax_and_changed_sku_are_preserved(self):
        plan = self.compile()[0]
        self.assertEqual(plan['total'], '31.81')
        self.assertEqual(plan['lines'][0]['tax'], '1.91')
        self.assertEqual(plan['lines'][0]['original_tax'], 1.92)
        self.assertEqual(plan['lines'][0]['sku'], 'old-sku')
        self.assertEqual(plan['lines'][0]['erp_item'], 'current-sku')
        self.assertEqual(plan['lines'][0]['woo_product_id'], 34)

    def test_delivered_does_not_imply_payment(self):
        self.source['orders'][0]['paymentStatus'] = 'AWAITING_PAYMENT'
        self.assertEqual(self.compile()[0]['status'], 'on-hold')

    def test_paid_open_order_is_not_completed(self):
        self.source['orders'][0]['fulfillmentStatus'] = 'AWAITING_PROCESSING'
        self.assertEqual(self.compile()[0]['status'], 'processing')

    def test_paid_sale_without_woo_login_keeps_erp_customer_and_guest_identity(self):
        self.woo['users'] = []
        self.erp['customer_woo'] = {}
        plan = self.compile()[0]
        self.assertEqual(plan['woo_customer_id'], 0)
        self.assertEqual(plan['erp_customer'], 'Existing Buyer')
        self.assertEqual(plan['email'], 'buyer@example.invalid')

    def test_unpaid_unfulfilled_checkout_is_excluded(self):
        self.source['orders'][0].update(paymentStatus='AWAITING_PAYMENT', fulfillmentStatus='AWAITING_PROCESSING')
        self.assertEqual(self.compile(), [])

    def test_missing_linked_woo_account_still_stops(self):
        self.woo['users'] = []
        with self.assertRaisesRegex(ValueError, 'missing Woo account'):
            self.compile()

    def test_refund_status_does_not_invent_refund_amount(self):
        self.source['orders'][0].update(paymentStatus='REFUNDED', refundedAmount=0)
        plan = self.compile()[0]
        self.assertEqual(plan['status'], 'refunded')
        self.assertEqual(plan['reported_refund'], '0')

    def test_discount_keeps_tax_and_total_exact(self):
        self.source['orders'][0].update(total='30.91', discount='0.90')
        self.assertEqual(self.compile()[0]['lines'][0]['net'], '29.00')

    def test_retired_product_remains_a_historical_line(self):
        self.woo['products'] = []
        self.erp['items'] = {}
        line = self.compile()[0]['lines'][0]
        self.assertEqual(line['woo_product_id'], 0)
        self.assertEqual(line['erp_item'], 'ECWID-HIST-10')
        self.assertTrue(line['create_item'])

    def test_newly_created_fallback_does_not_change_retry_plan(self):
        self.woo['products'] = []
        self.erp['items'] = {}
        before = self.compile()
        self.erp['items']['ECWID-HIST-10'] = True
        self.assertEqual(before, self.compile())

    def test_ambiguous_and_unresolved_customers_stop(self):
        self.erp['email_customers']['buyer@example.invalid'].append('Other Buyer')
        with self.assertRaisesRegex(ValueError, 'Ambiguous'):
            self.compile()
        self.erp['email_customers'] = {}
        self.erp['woo_customers'] = {}
        with self.assertRaisesRegex(ValueError, 'Unresolved'):
            self.compile()

    def test_duplicate_source_or_bad_money_stops(self):
        self.source['orders'].append(copy.deepcopy(self.source['orders'][0]))
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            self.compile()
        self.source['orders'].pop()
        self.source['orders'][0]['total'] = '31.82'
        with self.assertRaisesRegex(ValueError, 'balance'):
            self.compile()

    def test_cent_allocation_is_exact_and_stable(self):
        self.assertEqual(module.allocate('0.01', ['1.00', '1.00']), ['0.01', '0.00'])
        self.assertEqual(module.allocate('0', ['0', '0']), ['0.00', '0.00'])
        with self.assertRaises(ValueError):
            module.allocate('1', ['0'])


if __name__ == '__main__':
    unittest.main()
