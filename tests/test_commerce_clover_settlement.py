import unittest

from test_commerce_order_pilot import ROOT
from rootedops_commerce.settlement_contract import settlement_plan


class CloverSettlement(unittest.TestCase):
    def setUp(self):
        self.policy = dict(merchant='MID', environment='live', currency='USD', company='Company',
                           bank='Bank', fees='Fees', clearing_by_channel={'woo': 'Woo Clearing', 'pos': 'POS Clearing'},
                           adjustments={'reserve_withheld': {'account': 'Merchant Reserve', 'side': 'debit'}})
        self.batch = dict(merchant='MID', environment='live', reference='FUND-1', currency='USD',
                          source='merchant_statement', source_sha256='c' * 64,
                          bank={'reference': 'ACH-1', 'date': '2026-11-16', 'amount': '95', 'kind': 'deposit'},
                          net='95', gross='100', kind='deposit', records=[
                              dict(kind='capture', reference='WOO-1', amount='60', channel='woo', erp_reference='Payment Entry:WO-1'),
                              dict(kind='capture', reference='POS-1', amount='40', channel='pos', erp_reference='Journal Entry:POS-1'),
                              dict(kind='processing_fee', reference='FEE-1', amount='3'),
                              dict(kind='reserve_withheld', reference='RES-1', amount='2'),
                          ])

    def rows(self):
        return {row['account']: (row['debit_in_account_currency'], row['credit_in_account_currency'])
                for row in settlement_plan(self.batch, self.policy)['accounts']}

    def test_mixed_net_deposit_and_actual_withheld_fee(self):
        self.assertEqual(self.rows(), {'Bank': ('95', '0'), 'Fees': ('3', '0'),
                         'Merchant Reserve': ('2', '0'), 'POS Clearing': ('0', '40'),
                         'Woo Clearing': ('0', '60')})

    def test_separately_billed_fees(self):
        self.batch.update(kind='separate_fee_debit', net='3', gross='0', records=[self.batch['records'][2]])
        self.batch['bank'].update(kind='separate_fee_debit', amount='3')
        self.assertEqual(self.rows(), {'Bank': ('0', '3'), 'Fees': ('3', '0')})

    def test_out_of_balance_unclassified_and_duplicate(self):
        row = self.batch['records'][-1]
        row['amount'] = '4'
        with self.assertRaisesRegex(ValueError, 'Out-of-balance'):
            self.rows()
        row.update(amount='2', kind='unknown')
        with self.assertRaisesRegex(ValueError, 'classification'):
            self.rows()
        row.update(kind='reserve_withheld', reference='POS-1')
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            self.rows()
