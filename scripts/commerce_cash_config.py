#!/usr/bin/env python3
"""Merge reviewed cash configuration into a private ERP site config copy."""
import argparse
import json
import os
import re
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
def wordpress_env(source, enabled):
 if enabled not in ('0','1'):raise ValueError('Explicit cash flag 0 or 1 required')
 pattern=r'^(?:export\s+)?DANK_MP_CASH_ENABLED\s*=.*$'
 matches=re.findall(pattern,source,re.M)
 if len(matches)>1:raise ValueError('Duplicate cash flags require review')
 line='DANK_MP_CASH_ENABLED='+enabled
 return re.sub(pattern,line,source,flags=re.M) if matches else source.rstrip('\n')+'\n'+line+'\n'

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--site-config',type=Path);p.add_argument('--cash-config',type=Path);p.add_argument('--wordpress-env',type=Path);p.add_argument('--cash-enabled',choices=('0','1'));p.add_argument('--output',type=Path,required=True)
 a=p.parse_args()
 inputs=[a.wordpress_env] if a.wordpress_env else [a.site_config,a.cash_config]
 if any(path is None for path in inputs):p.error('Choose a private WordPress env plus --cash-enabled, or both ERP config inputs')
 for path in inputs:
  if path.stat().st_mode & 0o077:raise ValueError('Private input mode 600 required')
 if a.wordpress_env:
  result=wordpress_env(a.wordpress_env.read_text(),a.cash_enabled)
 else:
  result=json.dumps(merge(json.loads(a.site_config.read_text()),json.loads(a.cash_config.read_text())),indent=2)+'\n'
 with os.fdopen(os.open(a.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as f:f.write(result)
 print('Wrote private configuration copy; existing settings preserved. No deployment performed.')
if __name__=='__main__':main()
