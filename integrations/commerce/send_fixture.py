#!/usr/bin/env python3
"""Sign and POST a synthetic raw fixture to the local staging receiver only."""
import argparse
import base64
import hmac
import os
from pathlib import Path
import re
from urllib.request import Request,urlopen

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('fixture',type=Path);p.add_argument('--site',required=True)
p.add_argument('--secret-env',default='COMMERCE_WOO_SECRET');a=p.parse_args()
if os.environ.get('COMMERCE_STAGING_ONLY')!='1' or not re.fullmatch('[A-Za-z0-9_-]+',a.site):p.error('Explicit staging opt-in and simple test site key required')
secret=os.environ[a.secret_env]
if len(secret)<32:p.error('Strong test webhook secret required')
raw=a.fixture.read_bytes()
if len(raw)>2*1024*1024:p.error('Fixture exceeds receiver limit')
signature=base64.b64encode(hmac.digest(secret.encode(),raw,'sha256')).decode()
req=Request('http://127.0.0.1:8100/webhooks/woocommerce/'+a.site,data=raw,
            headers={'Content-Type':'application/json','X-WC-Webhook-Signature':signature},method='POST')
with urlopen(req,timeout=20) as response:print(response.read().decode())
