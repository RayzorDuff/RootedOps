"""The signed Woo action carries a scoped digest and stable ID, without profile data."""
import json
import re
import subprocess
import sys

from orders import authenticate

PROVIDER = 'woocommerce-customer'
ACTION = 'woocommerce_rootedops_customer_profile_saved'
LEGACY_ACTION = 'rootedops_customer_profile_saved'


def normalize_signal(raw, signature, secrets, site):
    receipt = authenticate(raw, signature, secrets)
    body = json.loads(raw)
    if (not isinstance(body, dict) or set(body) != {'action', 'arg'}
            or body['action'] not in (ACTION, LEGACY_ACTION)):
        raise ValueError('Unknown customer action')
    event = body['arg']
    if not isinstance(event, dict) or set(event) != {'id', 'scope', 'event', 'digest'}:
        raise ValueError('Invalid customer signal')
    if (type(event['id']) is not int or not 0 < event['id'] < 2**63
            or event['scope'] not in ('registered', 'account', 'billing', 'shipping')
            or not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', event['event'])
            or not re.fullmatch(r'[0-9a-f]{64}', event['digest'])):
        raise ValueError('Invalid customer signal')
    return dict(event, site_key=site, event_id=receipt, provider=PROVIDER,
                external_order_id=str(event['id']), revision=0)


def request_erp_customer(url, authorization, method, payload):
    """Use the curl transport accepted by the ERP ingress for customer POSTs."""
    if not url.startswith('https://') or method != 'POST':
        raise ValueError('Customer delivery requires an HTTPS POST')
    if any(ord(char) < 32 for char in authorization):
        raise ValueError('Invalid ERP authorization header')

    # Read the credential from stdin so it never appears in argv or the journal.
    header = 'header = ' + json.dumps('Authorization: ' + authorization) + '\n'
    result = subprocess.run(
        ['curl', '--disable', '--config', '-', '--silent', '--max-time', '60',
         '--proto', '=https', '--header', 'Content-Type: application/json',
         '--data-binary', json.dumps(payload), '--write-out', '\n%{http_code}', url],
        input=header, text=True, capture_output=True, check=False,
    )
    if result.returncode:
        print(f'ERP customer request: curl exit {result.returncode}', file=sys.stderr)
        raise RuntimeError('ERP customer request failed')
    body, _, code = result.stdout.rpartition('\n')
    if code != '200':
        status = code if re.fullmatch(r'[0-9]{3}', code) else 'unknown'
        print(f'ERP customer request: HTTP {status}', file=sys.stderr)
        raise RuntimeError('ERP customer request rejected')
    return json.loads(body)


def deliver_customer(inbox, erp_base, authorization, request, *, site):
    claim = inbox.claim(provider=PROVIDER, site=site, lease_seconds=300)
    if not claim:
        return False
    try:
        payload = {field: claim['payload'][field] for field in ('site_key', 'id', 'scope', 'digest')}
        receipt = claim['erp_receipt']
        if receipt is None:
            result = request(
                erp_base + '/api/method/rootedops_commerce.customer_sync.consume_signal',
                authorization, 'POST', {'payload': json.dumps(payload)},
            )['message']
            receipt = {'status': result['status']}
            if receipt['status'] == 'awaiting_registration':
                inbox.fail(claim, 'mapping_review')
                return True
            inbox.record(claim, 'erp', receipt)
        inbox.record(claim, 'mp', {'status': 'not_applicable'})
        inbox.finish(claim)
    except Exception:
        inbox.fail(claim, 'target_error')
    return True
