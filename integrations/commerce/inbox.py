"""Durable authenticated receipt and leased, retryable MP -> ERP delivery.

HTTP receipt only acknowledges durable storage. Cross-system effects are at-least
once: downstream operations MUST use the event/order identities idempotently.
"""
import json
from pathlib import Path
import uuid
from orders import normalize_woo


class Inbox:
    def __init__(self, connect):
        self.connect = connect

    def receive(self, raw, signature, *, secrets, site, mappings, gateways):
        event = normalize_woo(raw, signature, secrets, site, mappings, gateways)
        key = (event['provider'], site, event['event_id'])
        with self.connect() as db:
            old = db.execute('SELECT payload FROM commerce_inbox WHERE provider=%s AND site_key=%s AND event_id=%s', key).fetchone()
            if old:
                if old[0] != event:
                    raise ValueError('Event identity/configuration drift')
                return {'event_id': event['event_id'], 'duplicate': True}
            inserted = db.execute('''INSERT INTO commerce_inbox(provider,site_key,event_id,external_order_id,revision,payload)
                VALUES(%s,%s,%s,%s,%s,%s::jsonb) ON CONFLICT DO NOTHING RETURNING event_id''',
                (*key,event['external_order_id'],event['revision'],json.dumps(event))).fetchone()
            if not inserted:
                old = db.execute('SELECT payload FROM commerce_inbox WHERE provider=%s AND site_key=%s AND event_id=%s',key).fetchone()
                if old[0] != event:raise ValueError('Event identity/configuration drift')
            db.execute('INSERT INTO commerce_delivery(provider,site_key,event_id) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING',key)
        return {'event_id': event['event_id'], 'duplicate': not bool(inserted)}

    def claim(self, lease_seconds=60):
        token=uuid.uuid4().hex
        with self.connect() as db:
            row=db.execute('''SELECT d.provider,d.site_key,d.event_id,i.payload,d.mp_receipt,d.erp_receipt
                FROM commerce_delivery d JOIN commerce_inbox i USING(provider,site_key,event_id)
                WHERE (d.state='pending' AND d.next_attempt_at<=now())
                   OR (d.state='leased' AND d.lease_until<now())
                ORDER BY i.received_at FOR UPDATE OF d SKIP LOCKED LIMIT 1''').fetchone()
            if not row:return None
            db.execute('''UPDATE commerce_delivery SET state='leased',attempts=attempts+1,
                lease_token=%s,lease_until=now()+(%s * interval '1 second')
                WHERE provider=%s AND site_key=%s AND event_id=%s''',(token,lease_seconds,*row[:3]))
        return {'key':row[:3],'payload':row[3],'mp_receipt':row[4],'erp_receipt':row[5],'token':token}

    def record(self, claim, target, receipt):
        if target not in ('mp','erp'):raise ValueError('Unknown target')
        # Identifier comes from a fixed internal enum, never request data.
        with self.connect() as db:
            row=db.execute(f'''UPDATE commerce_delivery SET {target}_receipt=%s::jsonb
                WHERE provider=%s AND site_key=%s AND event_id=%s AND state='leased'
                AND lease_token=%s AND lease_until>=now() RETURNING event_id''',
                (json.dumps(receipt),*claim['key'],claim['token'])).fetchone()
            if not row:raise ValueError('Delivery lease lost')

    def finish(self, claim):
        with self.connect() as db:
            row=db.execute('''UPDATE commerce_delivery SET state='done',lease_token=NULL,lease_until=NULL,last_error=NULL
                WHERE provider=%s AND site_key=%s AND event_id=%s AND lease_token=%s
                AND state='leased' AND lease_until>=now() AND mp_receipt IS NOT NULL AND erp_receipt IS NOT NULL
                RETURNING event_id''',(*claim['key'],claim['token'])).fetchone()
            if not row:raise ValueError('Incomplete delivery or lost lease')

    def fail(self, claim, error_code, max_attempts=5, retry_seconds=30):
        # Never persist exception text, response bodies, tokens or customer data.
        if error_code not in ('target_error','mapping_review','revision_conflict'):
            raise ValueError('Use a safe error code')
        with self.connect() as db:
            db.execute('''UPDATE commerce_delivery SET state=CASE WHEN attempts>=%s THEN 'dead' ELSE 'pending' END,
                next_attempt_at=now()+(%s * interval '1 second'),last_error=%s,lease_token=NULL,lease_until=NULL
                WHERE provider=%s AND site_key=%s AND event_id=%s AND lease_token=%s''',
                (max_attempts,retry_seconds,error_code,*claim['key'],claim['token']))

    def replay(self, key):
        with self.connect() as db:
            row=db.execute('''UPDATE commerce_delivery SET state='pending',attempts=0,next_attempt_at=now(),last_error=NULL
                WHERE provider=%s AND site_key=%s AND event_id=%s AND state='dead' RETURNING event_id''',key).fetchone()
            if not row:raise ValueError('Only a dead letter can be replayed')

    def status(self):
        with self.connect() as db:
            return db.execute('''SELECT state,last_error,count(*) FROM commerce_delivery
                GROUP BY state,last_error ORDER BY state,last_error''').fetchall()


def deliver_one(inbox, mp_target, erp_target, *, max_attempts=5, retry_seconds=30):
    claim=inbox.claim()
    if not claim:return False
    try:
        mp=claim['mp_receipt']
        if mp is None:
            mp=mp_target(claim['payload'])
            inbox.record(claim,'mp',mp)
        if mp.get('status')=='stale':
            # A stale snapshot must not create/change an ERP commercial document.
            erp={'status':'stale_skipped'}
        elif claim['erp_receipt'] is None:
            erp=erp_target(claim['payload'],mp)
        else:erp=claim['erp_receipt']
        inbox.record(claim,'erp',erp)
        if erp.get('sales_order') and hasattr(mp_target,'link_erp'):
            mp_target.link_erp(claim['payload'],erp)
        inbox.finish(claim)
    except Exception:
        inbox.fail(claim,'target_error',max_attempts,retry_seconds)
    return True


class PostgresInventory:
    def __init__(self,connect):self.connect=connect
    def __call__(self,event):
        with self.connect() as db:
            status=db.execute('SELECT public.mp_commerce_ingest(%s::jsonb)',(json.dumps(event),)).fetchone()[0]
        return {'status':status,'provider':event['provider'],'site_key':event['site_key'],
                'external_order_id':event['external_order_id']}

    def link_erp(self,event,receipt):
        payload={k:event[k] for k in ('provider','site_key','external_order_id')}
        payload.update(erp_site='erp-test.danks.store',sales_order=receipt['sales_order'],
                       sales_invoice=receipt.get('sales_invoice'),payment_entry=receipt.get('payment_entry'))
        with self.connect() as db:
            return db.execute('SELECT public.mp_commerce_link_erp(%s::jsonb)',(json.dumps(payload),)).fetchone()[0]


class ReviewedERP:
    """Transport adapter: order-specific commercial draft must be reviewed first."""
    def __init__(self,base,authorization,approved,request):
        from urllib.parse import urlsplit
        p=urlsplit(base)
        if p.scheme!='https' or p.hostname!='erp-test.danks.store' or p.username or p.password or p.port not in (None,443):
            raise ValueError('ERP adapter requires approved staging origin')
        self.base=base.rstrip('/');self.authorization=authorization;self.approved=approved;self.request=request
    def __call__(self,event,mp_receipt):
        key='|'.join([event['provider'],event['site_key'],event['external_order_id']])
        draft=self.approved[key]
        payload={'event':event,'reviewed_draft':draft}
        return self.request(self.base+'/api/method/rootedops_commerce.order_service.stage_order',
                            self.authorization,'POST',{'payload':json.dumps(payload)})['message']


def application(inbox,sites):
    """Loopback WSGI boundary; reverse-proxy deployment remains opt-in."""
    def app(environ,start_response):
        status='202 Accepted';result={}
        try:
            if environ.get('REQUEST_METHOD')!='POST':raise ValueError('method')
            if environ.get('wsgi.url_scheme')!='https' and environ.get('SERVER_NAME') not in ('127.0.0.1','localhost'):
                raise ValueError('transport')
            path=environ.get('PATH_INFO','').split('/')
            if len(path)!=4 or path[1:3]!=['webhooks','woocommerce']:raise ValueError('route')
            config=sites[path[3]]
            size=int(environ.get('CONTENT_LENGTH',''))
            if not 0<size<=2*1024*1024:raise ValueError('size')
            if environ.get('CONTENT_TYPE','').split(';')[0]!='application/json':raise ValueError('content type')
            raw=environ['wsgi.input'].read(size)
            if len(raw)!=size:raise ValueError('truncated')
            result=inbox.receive(raw,environ.get('HTTP_X_WC_WEBHOOK_SIGNATURE',''),
                                 site=path[3],**config)
        except (ValueError,KeyError,TypeError):
            status='400 Bad Request';result={'error':'invalid_webhook'}
        except Exception:
            status='503 Service Unavailable';result={'error':'receipt_unavailable'}
        body=json.dumps(result).encode()
        start_response(status,[('Content-Type','application/json'),('Content-Length',str(len(body)))])
        return [body]
    return app
