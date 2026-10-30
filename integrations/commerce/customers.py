"""Exact-source Woo customer identity adapter; staging mail sink is mandatory."""
from urllib.parse import urlencode,urlsplit
from ecwid_migrate import api,digest


def upsert_customer(base,authorization,source_key,reviewed,*,mail_sink_verified=False,request=api):
    origin=urlsplit(base)
    if origin.scheme!='https' or origin.hostname!='shop-test.danks.store' or origin.username or origin.password or origin.port not in (None,443):
        raise ValueError('Exact staging origin required')
    if mail_sink_verified is not True:raise ValueError('Verify test-only email/external isolation before account creation')
    allowed={'email','first_name','last_name','billing','shipping'}
    if set(reviewed)-allowed or not reviewed.get('email') or not source_key:raise ValueError('Reviewed source/customer fields required')
    address_fields={'first_name','last_name','company','address_1','address_2','city','state','postcode','country','email','phone'}
    for kind in ['billing','shipping']:
        if set(reviewed.get(kind,{}))-address_fields:raise ValueError('Unsupported customer address fields')
        if reviewed.get(kind) and (len(reviewed[kind].get('country',''))!=2 or not reviewed[kind]['country'].isupper()):
            raise ValueError('Reviewed ISO country mapping required')
    root=base.rstrip('/')+'/wp-json/wc/v3/customers'
    rows=request(root+'?'+urlencode({'email':reviewed['email'],'per_page':100}),authorization)
    rows=[r for r in rows if r['email'].casefold()==reviewed['email'].casefold()]
    if len(rows)>1:raise ValueError('Ambiguous customer email')
    fingerprint=digest(reviewed)
    if rows:
        meta={m['key']:m['value'] for m in rows[0].get('meta_data',[])}
        if meta.get('_rootedops_source_key')!=source_key or meta.get('_rootedops_customer_hash')!=fingerprint:
            raise ValueError('Existing account is unowned or changed; explicit identity reconciliation required')
        return {'external_customer_id':rows[0]['id'],'source_key':source_key,'created':False}
    body=dict(reviewed,username='ro-'+digest(source_key)[:24],
              meta_data=[{'key':'_rootedops_source_key','value':source_key},{'key':'_rootedops_customer_hash','value':fingerprint}])
    result=request(root,authorization,'POST',body)
    return {'external_customer_id':result['id'],'source_key':source_key,'created':True}
