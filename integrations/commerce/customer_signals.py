"""The signed Woo action carries a scoped digest and stable ID, without profile data."""
import json
import re

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
