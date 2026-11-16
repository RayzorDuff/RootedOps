"""Accounts Manager can draft a balanced Journal Entry on an isolated site."""
from decimal import Decimal
import json

import frappe

from rootedops_commerce.clover_payment import STAGING
from rootedops_commerce.external_receipt import finish, lock_receipt
from rootedops_commerce.settlement_contract import settlement_plan
from rootedops_commerce.tax_contract import _money


@frappe.whitelist(methods=['POST'])
def draft_settlement(payload):
    if not {'System Manager', 'Accounts Manager'} & set(frappe.get_roles()):
        frappe.throw('Commerce finance role required', frappe.PermissionError)
    config = frappe.conf.get('commerce_clover_settlement_pilot') or {}
    if frappe.local.site not in STAGING or config.get('enabled') is not True:
        raise ValueError('Isolated Clover settlement draft pilot required')
    batch = frappe.parse_json(payload)
    plan = settlement_plan(batch, config)
    identity = [plan['environment'], plan['merchant'], plan['reference']]
    receipt = lock_receipt('clover_funding', identity, {'batch': batch, 'plan': plan})
    if receipt.result:
        prior = json.loads(receipt.result)
        journal = frappe.get_doc('Journal Entry', prior['journal_entry'])
        journal.check_permission('read')
        expected = _amounts(plan['accounts'])
        actual = _amounts(journal.accounts)
        if (journal.docstatus != 0 or journal.company != plan['company'] or actual != expected
                or str(journal.posting_date) != plan['posting_date'] or journal.cheque_no != plan['bank_reference']):
            raise ValueError('Existing settlement draft needs reconciliation')
        return prior
    bank_key = lock_receipt('clover_bank_line', [plan['company'], config['bank'], plan['bank_reference']], identity)
    lines = [lock_receipt('clover_funding_line', identity[:2] + [key], identity) for key in plan['funding_ids']]
    lines.extend(_validate_clearing(plan, identity))
    if bank_key.result or any(line.result for line in lines):
        raise ValueError('Bank or funding reference already reconciled')
    company = frappe.get_doc('Company', plan['company'])
    company.check_permission('read')
    if company.default_currency != plan['currency']:
        raise ValueError('Cross-currency Clover settlement requires review')
    bank = config['bank']
    fees = config['fees']
    clearing = set(config['clearing_by_channel'].values())
    if len({bank, fees}) != 2 or {bank, fees} & clearing:
        raise ValueError('Bank, clearing and processing expense must be different Accounts')
    for row in plan['accounts']:
        account = frappe.get_doc('Account', row['account'])
        account.check_permission('read')
        if (account.company != plan['company'] or account.account_currency != plan['currency']
                or account.disabled or account.is_group
                or account.name == bank and account.account_type != 'Bank'
                or account.name == fees and account.root_type != 'Expense'
                or account.name in clearing and account.root_type != 'Asset'):
            raise ValueError('Settlement Account/company/currency mismatch')
    journal = frappe.get_doc(dict(doctype='Journal Entry', voucher_type='Bank Entry',
        company=plan['company'], posting_date=plan['posting_date'], cheque_no=plan['bank_reference'],
        cheque_date=plan['posting_date'], user_remark='Clover funding ' + plan['reference'],
        accounts=plan['accounts'])).insert()
    if _amounts(journal.accounts) != _amounts(plan['accounts']):
        raise ValueError('Native Journal Entry differs from approved funding amounts')
    result = dict(status='draft', journal_entry=journal.name, settlement_reference=plan['reference'])
    for row in [bank_key, *lines, receipt]:
        finish(row, result)
    return result


def _validate_clearing(plan, identity):
    receipts = []
    for match in plan['clearing_vouchers']:
        doctype, separator, name = match['voucher'].partition(':')
        if not separator or not name or doctype not in ('Payment Entry', 'Sales Invoice', 'Journal Entry', 'POS Invoice'):
            raise ValueError('Approved ERP clearing voucher reference required')
        doc = frappe.get_doc(doctype, name)
        doc.check_permission('read')
        if (doc.docstatus != 1 or doc.company != plan['company']
                or str(doc.posting_date) > plan['posting_date']):
            raise ValueError('Posted clearing voucher must precede the funding deposit')
        rows = frappe.get_all('GL Entry', filters=dict(company=plan['company'], account=match['account'],
            voucher_type=doctype, voucher_no=name, is_cancelled=0), fields=['debit', 'credit'])
        total = sum(_money(row.debit) - _money(row.credit) for row in rows)
        if not rows or not total or total != Decimal(match['amount']):
            raise ValueError('Funding lines do not tie to the posted clearing voucher')
        receipts.append(lock_receipt('clover_clearing_voucher',
            [plan['company'], match['account'], doctype, name], identity))
    return receipts


def _amounts(rows):
    return sorted((row.get('account'), _money(row.get('debit_in_account_currency') or 0),
                   _money(row.get('credit_in_account_currency') or 0)) for row in rows)
