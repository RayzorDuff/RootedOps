"""Exact-source Woo customer identity adapter; staging mail sink is mandatory."""
from urllib.parse import urlencode,urlsplit
from ecwid_migrate import api,digest
from staging_origin import staging_origin


def owned_customer(row, source_key, fingerprint):
    meta={m['key']:m['value'] for m in row.get('meta_data',[])}
    # Woo 11 filters protected (underscore-prefixed) user meta on REST writes.
    # Read legacy identities where available; never adopt an unowned email.
    pairs=[(meta.get(prefix+'rootedops_source_key'),meta.get(prefix+'rootedops_customer_hash'))
           for prefix in ('','_') if prefix+'rootedops_source_key' in meta or prefix+'rootedops_customer_hash' in meta]
    return bool(pairs) and all(pair==(source_key,fingerprint) for pair in pairs)


def upsert_customer(base,authorization,source_key,reviewed,*,mail_sink_verified=False,request=api):
    base=staging_origin(base,'shop')
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
        if not owned_customer(rows[0],source_key,fingerprint):
            raise ValueError('Existing account is unowned or changed; explicit identity reconciliation required')
        return {'external_customer_id':rows[0]['id'],'source_key':source_key,'created':False}
    body=dict(reviewed,username='ro-'+digest(source_key)[:24],
              meta_data=[{'key':'rootedops_source_key','value':source_key},{'key':'rootedops_customer_hash','value':fingerprint}])
    result=request(root,authorization,'POST',body)
    stored=request(root+'/'+str(result['id'])+'?context=edit',authorization)
    if not owned_customer(stored,source_key,fingerprint):
        raise ValueError('Created customer identity was not persisted; reconcile before retry')
    return {'external_customer_id':result['id'],'source_key':source_key,'created':True}
