"""Compile reviewed Clover funding detail and a matched bank entry into a draft."""
from collections import defaultdict
from datetime import date
import re

from rootedops_commerce.tax_contract import _money


def field(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 140:
        raise ValueError('Settlement requires reviewed references')
    return value.strip()


def settlement_plan(batch, policy):
    merchant = field(batch['merchant'])
    environment = batch['environment']
    if (environment not in ('sandbox', 'live') or policy['environment'] != environment
            or policy['merchant'] != merchant or batch['currency'] != policy['currency']):
        raise ValueError('Settlement merchant, environment or currency mismatch')
    if (batch.get('source') not in ('funding_report', 'merchant_statement', 'verified_funding_api')
            or not re.fullmatch(r'[0-9a-f]{64}', batch.get('source_sha256', ''))):
        raise ValueError('Reviewed funding detail and source checksum required')
    reference = field(batch['reference'])
    bank = batch['bank']
    bank_reference = field(bank['reference'])
    posting_date = date.fromisoformat(bank['date']).isoformat()
    settlement_kind = batch['kind']
    if settlement_kind not in ('deposit', 'separate_fee_debit') or bank['kind'] != settlement_kind:
        raise ValueError('Exact deposit or fee debit bank classification required')
    amount = _money(bank['amount'])
    if not amount or _money(batch['net']) != amount:
        raise ValueError('Funding amount differs from the bank')
    balances = defaultdict(lambda: 0)
    balances[policy['bank']] = amount if settlement_kind == 'deposit' else -amount
    seen = set()
    capture = False
    clearing_vouchers = defaultdict(lambda: 0)
    for row in batch['records']:
        kind = row['kind']
        identity = field(row['reference'])
        if identity in seen:
            raise ValueError('Duplicate funding line identity')
        seen.add(identity)
        value = _money(row['amount'])
        if not value:
            raise ValueError('Funding lines must carry a positive amount')
        if settlement_kind == 'separate_fee_debit':
            if kind != 'processing_fee' or row.get('channel'):
                raise ValueError('Separately billed fee debit requires only actual fee lines')
            balances[policy['fees']] += value
        elif kind in ('capture', 'refund_clearing', 'chargeback_clearing'):
            account = policy['clearing_by_channel'].get(field(row.get('channel')))
            if not account:
                raise ValueError('Funding channel or adjustment needs clearing review')
            voucher = field(row.get('erp_reference'))
            if kind == 'capture':
                capture = True
                balances[account] -= value
                clearing_vouchers[(account, voucher)] += value
            else:
                balances[account] += value
                clearing_vouchers[(account, voucher)] -= value
        elif kind == 'processing_fee':
            balances[policy['fees']] += value
        else:
            rule = policy.get('adjustments', {}).get(kind)
            if not rule or rule['side'] not in ('debit', 'credit'):
                raise ValueError('Funding adjustment needs approved classification')
            balances[rule['account']] += value if rule['side'] == 'debit' else -value
    if not seen or (settlement_kind == 'deposit' and not capture) or sum(balances.values()):
        raise ValueError('Out-of-balance funding batch requires review')
    return dict(merchant=merchant, environment=environment, reference=reference, bank_reference=bank_reference,
                posting_date=posting_date, currency=batch['currency'], company=policy['company'],
                accounts=[dict(account=account, debit_in_account_currency=str(max(0, value)),
                               credit_in_account_currency=str(max(0, -value)))
                          for account, value in sorted(balances.items()) if value],
                funding_ids=sorted(seen),
                clearing_vouchers=[dict(account=account, voucher=voucher, amount=str(value))
                                   for (account, voucher), value in sorted(clearing_vouchers.items())])
