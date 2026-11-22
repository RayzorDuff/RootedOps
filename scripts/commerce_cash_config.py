#!/usr/bin/env python3
"""Merge reviewed cash configuration into a private ERP site config copy."""
import argparse
import json
import os
from pathlib import Path
ALLOWED={'enabled','evidence_hmac','company','cash_account','mode_of_payment','approved_orders'}
def merge(site,patch):
 if set(patch)-ALLOWED:raise ValueError('Unknown cash configuration key')
 cash=dict(site.get('commerce_cash_accounting') or {})
 cash.update(patch)
 if type(cash.get('enabled')) is not bool:raise ValueError('Explicit enabled flag required')
 if cash['enabled']:
  if len(cash.get('evidence_hmac') or '')<32 or not cash.get('company') or not cash.get('cash_account') or not isinstance(cash.get('approved_orders'),dict):
   raise ValueError('Reviewed company, cash account, evidence key and approvals required')
 return dict(site,commerce_cash_accounting=cash)
def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--site-config',type=Path,required=True);p.add_argument('--cash-config',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
 a=p.parse_args()
 for path in [a.site_config,a.cash_config]:
  if path.stat().st_mode & 0o077:raise ValueError('Private input mode 600 required')
 result=merge(json.loads(a.site_config.read_text()),json.loads(a.cash_config.read_text()))
 with os.fdopen(os.open(a.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as f:json.dump(result,f,indent=2);f.write('\n')
 print('Wrote private configuration copy; existing settings preserved. No deployment performed.')
if __name__=='__main__':main()
