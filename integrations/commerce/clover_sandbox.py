"""Read-only Clover charge and merchant-payment evidence. No charge/capture/refund mutation methods.

Production fallback requires two authenticated, matching provider records.
Only this authenticated fetch boundary marks evidence verified; webhook payloads
must never be passed as transport responses by the receiver.
"""
import json
import re
from decimal import Decimal
from urllib.request import Request,build_opener,HTTPRedirectHandler
from orders import reconcile_clover

BASE='https://scl-sandbox.dev.clover.com/v1/charges/'
PRODUCTION_BASE='https://scl.clover.com/v1/charges/'


def get_charge(charge_id, private_key, *, production=False):
    if not isinstance(charge_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{5,128}',charge_id):
        raise ValueError('Invalid charge identity')
    if not isinstance(private_key,str) or len(private_key)<32 or any(c in private_key for c in '\r\n'):
        raise ValueError('Private sandbox key required')
    return _get_json((PRODUCTION_BASE if production else BASE)+charge_id, private_key)


def get_payment(payment_id, merchant_id, access_token):
    """Fixed production merchant-scoped GET; never capture or mutate a payment."""
    for value in (payment_id, merchant_id):
        if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{5,128}', value):
            raise ValueError('Invalid merchant payment identity')
    if not isinstance(access_token, str) or len(access_token) < 16 or any(c in access_token for c in '\r\n'):
        raise ValueError('Production platform token required')
    return _get_json('https://api.clover.com/v3/merchants/' + merchant_id +
                     '/payments/' + payment_id + '?expand=refunds,cardTransaction', access_token)


def _get_json(url, key):
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):raise ValueError('Clover redirect refused')
    request=Request(url,headers={'Authorization':'Bearer '+key,
        'Accept':'application/json','User-Agent':'RootedOps-Commerce/0.3 charge-reconciliation'},method='GET')
    try:
        with build_opener(NoRedirect).open(request,timeout=30) as response:
            body=response.read(1024*1024+1)
        if len(body)>1024*1024:raise ValueError('Oversize charge response')
        def unique(pairs):
            result={}
            for key,value in pairs:
                if key in result:raise ValueError('Ambiguous provider JSON')
                result[key]=value
            return result
        return json.loads(body,object_pairs_hook=unique)
    except Exception:
        # Never include keys, charge data/card details or provider response bodies.
        raise RuntimeError('Clover charge lookup failed; reconciliation remains unverified') from None


def cents(value):
    if type(value) is not int or value<0:raise ValueError('Integer nonnegative provider minor units required')
    return format(Decimal(value)/100,'.2f')


class CloverSandboxEvidence:
    def __init__(self, *, site_key, merchant_id, private_key, enabled=False, transport=None, production=False,
                 platform_token=None, payment_transport=None):
        if enabled is not True:raise ValueError('Explicit sandbox evidence opt-in required')
        allowed = ('danks.store',) if production else ('shop-test', 'shop-test.danks.store', 'shop-test2.danks.store', 'synthetic')
        if site_key not in allowed:
            raise ValueError('Clover environment/site mismatch')
        if not site_key or not re.fullmatch(r'[A-Za-z0-9_-]{5,64}',merchant_id):raise ValueError('Reviewed site/merchant binding required')
        if not isinstance(private_key,str) or len(private_key)<32 or any(c in private_key for c in '\r\n'):
            raise ValueError('Private sandbox key required')
        self.site, self.merchant, self._key = site_key, merchant_id, private_key
        if payment_transport is not None and not platform_token:
            raise ValueError('Platform transport requires its own credential')
        if platform_token is not None and (not production or not isinstance(platform_token, str)
                or len(platform_token) < 16 or any(c in platform_token for c in '\r\n')):
            raise ValueError('Production platform credential required')
        self._platform_token = platform_token
        self._payment_get = payment_transport or get_payment
        self.production = production
        self._get = transport or (lambda charge, key: get_charge(charge, key, production=production))

    def evidence(self, order, *, reviewed_order):
        if order['site_key']!=self.site or order['payment_processor']!='clover':raise ValueError('Site/processor binding mismatch')
        charge_id=order.get('processor_payment_id')
        if not isinstance(charge_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{5,128}',charge_id):
            raise ValueError('Exact reviewed Clover charge identity required')
        # Official Woo plugin uses display order number, not necessarily numeric ID.
        # Require the crosswalk explicitly rather than inferring equality.
        reviewed_order_number=reviewed_order.get('number')
        if str(reviewed_order.get('id'))!=str(order['external_order_id']) or not isinstance(reviewed_order_number,str) or not reviewed_order_number.strip():
            raise ValueError('Reviewed Woo display-number crosswalk required')
        if order['currency'] not in ('USD','CAD'):raise ValueError('Reviewed two-minor-unit currency required')
        try:charge=self._get(charge_id,self._key)
        except Exception:
            raise RuntimeError('Clover charge lookup failed; reconciliation remains unverified') from None
        corroborated = self.production and self._platform_token is not None
        if (not isinstance(charge,dict) or charge.get('id')!=charge_id
                or (charge.get('object') != 'charge' and not (corroborated and 'object' not in charge))):
            raise ValueError('Exact single charge response required')
        reported_merchant = charge.get('merchant_id')
        if reported_merchant is not None and reported_merchant != self.merchant:
            raise ValueError('Clover charge merchant mismatch')
        if charge.get('livemode') is not self.production and not (corroborated and 'livemode' not in charge):
            raise ValueError('Explicit Clover environment required')
        if charge.get('external_reference_id')!=reviewed_order_number:raise ValueError('Charge/order reference mismatch')
        if charge.get('status')!='succeeded' or charge.get('paid') is not True or (not corroborated and charge.get('captured') is not True):
            raise ValueError('Successful captured charge required; authorization/failed IDs are insufficient')
        if charge.get('currency')!=order['currency'].lower():raise ValueError('Charge currency mismatch')
        if corroborated:
            self._closed_payment(charge, reviewed_order_number)
        amount=cents(charge.get('amount'));captured=cents(charge.get('amount_captured'))
        refunded=cents(charge.get('amount_refunded', 0) if corroborated else charge.get('amount_refunded'))
        if amount!=captured or Decimal(refunded)>Decimal(captured):raise ValueError('Partial capture or invalid refund requires review')
        result={'verification':'verified_adapter','processor':'clover','state':'captured',
            'site_key':self.site,'merchant_id':self.merchant,'provider_environment':'production' if self.production else 'sandbox',
            'external_order_id':order['external_order_id'],'external_order_number':reviewed_order_number,
            'payment_id':charge_id,'processor_reference_type':'clover_ecommerce_charge',
            'currency':order['currency'],'captured_amount':captured,'refunded_amount':refunded}
        if corroborated:
            result['capture_verification'] = 'matching_merchant_payment_auth_closed'
        reconcile_clover(order,result)
        return result

    def _closed_payment(self, charge, order_number):
        try:
            payment = self._payment_get(charge['id'], self.merchant, self._platform_token)
        except Exception:
            raise RuntimeError('Clover merchant payment lookup failed; reconciliation remains unverified') from None
        if not isinstance(payment, dict):
            raise ValueError('Exact merchant payment response required')
        card = payment.get('cardTransaction') or {}
        refunds = payment.get('refunds')
        if (payment.get('id') != charge['id'] or payment.get('result') != 'SUCCESS'
                or payment.get('offline') is not False or payment.get('voided', False) is not False
                or payment.get('externalReferenceId') != order_number
                or not isinstance(card, dict) or card.get('type') != 'AUTH' or card.get('state') != 'CLOSED'
                or not isinstance(payment.get('order'), dict)
                or payment['order'].get('id') != charge.get('order') or not charge.get('order')
                or type(payment.get('amount')) is not int or payment['amount'] != charge.get('amount')):
            raise ValueError('Matching successful closed merchant payment required')
        # Missing refund information is unknown, not zero. Empty expanded
        # refunds plus the matching closed payment corroborate this charge.
        if (not isinstance(refunds, dict) or refunds.get('elements') != []
                or set(refunds) - {'elements', 'href'}
                or charge.get('amount_refunded', 0) != 0 or type(charge.get('amount_refunded', 0)) is not int
                or charge.get('refunded', False) is not False):
            raise ValueError('Explicit unrefunded merchant payment required')
        if 'captured' in charge and type(charge['captured']) is not bool:
            raise ValueError('Invalid Ecommerce capture field')
