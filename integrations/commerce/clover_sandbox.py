"""Read-only sandbox charge evidence. No charge/capture/refund mutation methods.

Strict contracts need verification against a real sandbox response before rollout.
Only this authenticated fetch boundary marks evidence verified; webhook payloads
must never be passed as transport responses by the receiver.
"""
import json
import re
from decimal import Decimal
from urllib.request import Request,build_opener,HTTPRedirectHandler
from orders import reconcile_clover

BASE='https://scl-sandbox.dev.clover.com/v1/charges/'


def get_charge(charge_id, private_key):
    if not isinstance(charge_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{5,128}',charge_id):
        raise ValueError('Invalid charge identity')
    if not isinstance(private_key,str) or len(private_key)<32 or any(c in private_key for c in '\r\n'):
        raise ValueError('Private sandbox key required')
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):raise ValueError('Clover redirect refused')
    request=Request(BASE+charge_id,headers={'Authorization':'Bearer '+private_key,
        'Accept':'application/json','User-Agent':'RootedOps-Commerce/0.3 sandbox-reconciliation'},method='GET')
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
        raise RuntimeError('Sandbox charge lookup failed; reconciliation remains unverified') from None


def cents(value):
    if type(value) is not int or value<0:raise ValueError('Integer nonnegative provider minor units required')
    return format(Decimal(value)/100,'.2f')


class CloverSandboxEvidence:
    def __init__(self, *, site_key, merchant_id, private_key, enabled=False, transport=get_charge):
        if enabled is not True:raise ValueError('Explicit sandbox evidence opt-in required')
        if site_key not in ('shop-test','synthetic'):raise ValueError('Dedicated sandbox site required')
        if not site_key or not re.fullmatch(r'[A-Za-z0-9_-]{5,64}',merchant_id):raise ValueError('Reviewed site/merchant binding required')
        if not isinstance(private_key,str) or len(private_key)<32 or any(c in private_key for c in '\r\n'):
            raise ValueError('Private sandbox key required')
        self.site,self.merchant,self._key,self._get=site_key,merchant_id,private_key,transport

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
            raise RuntimeError('Sandbox charge lookup failed; reconciliation remains unverified') from None
        if not isinstance(charge,dict) or charge.get('object')!='charge' or charge.get('id')!=charge_id:
            raise ValueError('Exact single charge response required')
        if charge.get('livemode') is not False:raise ValueError('Explicit sandbox response required')
        if charge.get('external_reference_id')!=reviewed_order_number:raise ValueError('Charge/order reference mismatch')
        if charge.get('status')!='succeeded' or charge.get('paid') is not True or charge.get('captured') is not True:
            raise ValueError('Successful captured charge required; authorization/failed IDs are insufficient')
        if charge.get('currency')!=order['currency'].lower():raise ValueError('Charge currency mismatch')
        amount=cents(charge.get('amount'));captured=cents(charge.get('amount_captured'));refunded=cents(charge.get('amount_refunded'))
        if amount!=captured or Decimal(refunded)>Decimal(captured):raise ValueError('Partial capture or invalid refund requires review')
        result={'verification':'verified_adapter','processor':'clover','state':'captured',
            'site_key':self.site,'merchant_id':self.merchant,'provider_environment':'sandbox',
            'external_order_id':order['external_order_id'],'external_order_number':reviewed_order_number,
            'payment_id':charge_id,'processor_reference_type':'clover_ecommerce_charge',
            'currency':order['currency'],'captured_amount':captured,'refunded_amount':refunded}
        reconcile_clover(order,result)
        return result
