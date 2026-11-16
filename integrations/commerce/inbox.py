"""Durable authenticated receipt and leased, retryable MP -> ERP delivery.

HTTP receipt only acknowledges durable storage. Cross-system effects are at-least
once: downstream operations MUST use the event/order identities idempotently.
"""
import json
from pathlib import Path
import uuid
from orders import OrderReview, authenticate, normalize_order, normalize_woo, woo_source


ORDER_REVIEW_CODES = {
    'order_status_review', 'order_payload_review', 'gateway_review', 'item_unmapped',
    'item_disabled', 'item_mapping_review', 'customer_mapping_review', 'commercial_review',
    'draft_review', 'revision_conflict', 'inventory_review',
}


def same_receipt(stored, incoming):
    if incoming.get('order_intake_mode') == 'unpaid_pilot_pending':
        # The raw SHA is the receipt identity. A worker may already have
        # materialized the signed source against the reviewed mappings.
        return all(stored.get(key) == value for key, value in incoming.items()
                   if key != 'order_intake_mode')
    # A replay of a pre-upgrade order has the same authenticated raw hash.
    # Older normalized rows omitted the registered/guest field.
    if stored.get('provider') == 'woocommerce' and 'external_customer_id' not in stored:
        incoming = {key: value for key, value in incoming.items() if key != 'external_customer_id'}
    return stored == incoming


class Inbox:
    def __init__(self, connect):
        self.connect = connect

    def receive(self, raw, signature, *, secrets, site, mappings=None, gateways=None,
                tax_policy=None, unpaid_pilot=False):
        if unpaid_pilot:
            receipt = authenticate(raw, signature, secrets)
            _, event = woo_source(raw, site, receipt)
            event['order_intake_mode'] = 'unpaid_pilot_pending'
        else:
            event = normalize_woo(raw, signature, secrets, site, mappings, gateways, tax_policy=tax_policy)
        return self.store(event, raw)

    def receive_customer(self, raw, signature, *, secrets, site):
        from customer_signals import normalize_signal
        return self.store(normalize_signal(raw, signature, secrets, site), raw)

    def store(self, event, raw):
        key = (event['provider'], event['site_key'], event['event_id'])
        with self.connect() as db:
            old = db.execute('SELECT payload FROM commerce_inbox WHERE provider=%s AND site_key=%s AND event_id=%s', key).fetchone()
            if old:
                if not same_receipt(old[0], event):
                    raise ValueError('Event identity/configuration drift')
                return {'event_id': event['event_id'], 'duplicate': True}
            inserted = db.execute('''INSERT INTO commerce_inbox(provider,site_key,event_id,external_order_id,revision,payload,raw_body)
                VALUES(%s,%s,%s,%s,%s,%s::jsonb,%s) ON CONFLICT DO NOTHING RETURNING event_id''',
                (*key,event['external_order_id'],event['revision'],json.dumps(event),raw)).fetchone()
            if not inserted:
                old = db.execute('SELECT payload FROM commerce_inbox WHERE provider=%s AND site_key=%s AND event_id=%s',key).fetchone()
                if not same_receipt(old[0], event):raise ValueError('Event identity/configuration drift')
            db.execute('INSERT INTO commerce_delivery(provider,site_key,event_id) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING',key)
        return {'event_id': event['event_id'], 'duplicate': not bool(inserted)}

    def claim(self, lease_seconds=60, *, provider="woocommerce", site=None):
        token=uuid.uuid4().hex
        with self.connect() as db:
            # A delayed or locked earlier receipt blocks later receipts for
            # the same order. Customer-signal ordering is unchanged.
            row=db.execute('''SELECT d.provider,d.site_key,d.event_id,i.payload,d.mp_receipt,d.erp_receipt,
                    CASE WHEN i.payload->>'order_intake_mode'='unpaid_pilot_pending'
                         THEN i.raw_body END
                FROM commerce_delivery d JOIN commerce_inbox i USING(provider,site_key,event_id)
                WHERE d.provider=%s AND (%s::text IS NULL OR d.site_key=%s)
                  AND ((d.state='pending' AND d.next_attempt_at<=now())
                    OR (d.state='leased' AND d.lease_until<now()))
                  AND (d.provider<>'woocommerce' OR NOT EXISTS (
                    SELECT 1 FROM commerce_inbox earlier
                    JOIN commerce_delivery prior USING(provider,site_key,event_id)
                    WHERE earlier.provider=i.provider AND earlier.site_key=i.site_key
                      AND earlier.external_order_id=i.external_order_id
                      AND prior.state IN ('pending','leased')
                      AND (earlier.received_at,earlier.event_id)<(i.received_at,i.event_id)))
                ORDER BY i.received_at,i.event_id FOR UPDATE OF d SKIP LOCKED LIMIT 1''',
                (provider,site,site)).fetchone()
            if not row:return None
            db.execute('''UPDATE commerce_delivery SET state='leased',attempts=attempts+1,
                lease_token=%s,lease_until=now()+(%s * interval '1 second')
                WHERE provider=%s AND site_key=%s AND event_id=%s''',(token,lease_seconds,*row[:3]))
        return {'key':row[:3],'payload':row[3],'mp_receipt':row[4],'erp_receipt':row[5],
                'raw_pending':row[6],'token':token}

    def materialize_order(self, claim, event):
        with self.connect() as db:
            lease = db.execute('''SELECT 1 FROM commerce_delivery
                WHERE provider=%s AND site_key=%s AND event_id=%s AND state='leased'
                AND lease_token=%s AND lease_until>=now() FOR UPDATE''',
                (*claim['key'], claim['token'])).fetchone()
            if not lease:
                raise ValueError('Delivery lease lost')
            db.execute('''UPDATE commerce_inbox SET payload=%s::jsonb
                WHERE provider=%s AND site_key=%s AND event_id=%s''',
                (json.dumps(event), *claim['key']))

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
        if error_code not in ORDER_REVIEW_CODES | {'target_error', 'mapping_review'}:
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

    def order_status(self, key):
        with self.connect() as db:
            rows = db.execute("""SELECT i.event_id,i.revision,d.state,d.last_error,d.mp_receipt,d.erp_receipt
                FROM commerce_inbox i JOIN commerce_delivery d USING(provider,site_key,event_id)
                WHERE i.provider=%s AND i.site_key=%s AND i.external_order_id=%s
                ORDER BY i.received_at,i.event_id""", key).fetchall()
        fields = ('event_id', 'revision', 'state', 'last_error', 'mushroomprocess', 'erp')
        return [dict(zip(fields, row)) for row in rows]

    def completed_order(self, key):
        with self.connect() as db:
            row=db.execute('''SELECT i.payload,d.state FROM commerce_inbox i
                JOIN commerce_delivery d USING(provider,site_key,event_id)
                WHERE i.provider=%s AND i.site_key=%s AND i.external_order_id=%s
                ORDER BY i.revision DESC,i.received_at DESC,i.event_id DESC LIMIT 1''',key).fetchone()
            if not row or row[1]!='done':raise ValueError('Latest order event must have completed delivery')
            return row[0]


def reconcile_order(inbox, mp_target, erp_target, key):
    """Refresh independently verified ERP references; no event/payment/stock replay."""
    event=inbox.completed_order(key)
    receipt=erp_target.resolve(event)
    mp_target.link_erp(event,receipt)
    return {'reconciled':True,'accounting_posted':False,'physical_fulfillment':False}


def deliver_one(inbox, mp_target, erp_target, *, max_attempts=5, retry_seconds=30,
                tax_policies=None, pilot_configs=None, site=None):
    claim = inbox.claim(site=site) if site else inbox.claim()
    if not claim:
        return False
    event = claim['payload']
    try:
        mode = event.get('order_intake_mode')
        if mode in ('unpaid_pilot_pending', 'unpaid_pilot'):
            config = (pilot_configs or {}).get(event['site_key'])
            if config is None:
                raise OrderReview('draft_review')
            # Require explicit admission before sending any demand to MP.
            erp_target.draft_for(event)
            if mode == 'unpaid_pilot_pending':
                order, identity = woo_source(bytes(claim['raw_pending']), event['site_key'], event['event_id'])
                try:
                    event = normalize_order(order, identity, **config)
                except OrderReview:
                    raise
                except (ValueError, TypeError, KeyError, ArithmeticError) as exc:
                    raise OrderReview('order_payload_review') from exc
                inbox.materialize_order(claim, event)
        elif tax_policies is not None:
            from tax_policy import require_approved_item
            policy = tax_policies.get(event['site_key'])
            if policy is None:
                raise ValueError('No owner-approved tax classification for site')
            for line in event['lines']:
                require_approved_item(line['erp_item_code'], policy)
        mp = claim['mp_receipt']
        if mp is None:
            mp = mp_target(event)
            inbox.record(claim, 'mp', mp)
        if (mp.get('status') == 'stale' or
                claim['mp_receipt'] is not None and claim['erp_receipt'] is None
                and hasattr(mp_target, 'is_stale') and mp_target.is_stale(event)):
            erp = {'status': 'stale_skipped'}
        elif claim['erp_receipt'] is None:
            erp = erp_target(event, mp)
        else:
            erp = claim['erp_receipt']
        inbox.record(claim, 'erp', erp)
        if erp.get('sales_order') and hasattr(mp_target, 'link_erp'):
            mp_target.link_erp(event, erp)
        inbox.finish(claim)
    except OrderReview as exc:
        inbox.fail(claim, exc.code, max_attempts=1, retry_seconds=0)
    except Exception:
        inbox.fail(claim, 'target_error', max_attempts, retry_seconds)
    return True


class PostgresInventory:
    def __init__(self,connect,erp_site='erp-test.danks.store'):
        from staging_origin import staging_origin
        from urllib.parse import urlsplit
        self.erp_site=urlsplit(staging_origin('https://'+erp_site,'erp')).hostname
        self.connect=connect
    def __call__(self,event):
        try:
            with self.connect() as db:
                if event.get('order_intake_mode') == 'unpaid_pilot' and event['status'] != 'cancelled':
                    self.verify_pilot_mappings(db, event)
                status=db.execute('SELECT public.mp_commerce_ingest(%s::jsonb)',(json.dumps(event),)).fetchone()[0]
        except Exception as exc:
            reason = getattr(getattr(exc, 'diag', None), 'message_primary', None)
            review_codes = {
                'Same-revision conflict; fetch current authoritative order': 'revision_conflict',
                'Unapproved operational mapping': 'item_mapping_review',
                'Insufficient sellable operational quantity': 'inventory_review',
                'Order line/currency/total edit requires manual reconciliation': 'commercial_review',
            }
            if reason in review_codes:
                raise OrderReview(review_codes[reason]) from exc
            raise
        return {'status':status,'provider':event['provider'],'site_key':event['site_key'],
                'external_order_id':event['external_order_id']}

    @staticmethod
    def verify_pilot_mappings(db, event):
        for line in event['lines']:
            source = event['line_sources'][line['line_id']]
            rows = db.execute("""SELECT ecommerce_id,erp_item_code
                FROM public.mp_ecommerce_catalog_inventory()
                WHERE provider=%s AND site_key=%s AND external_sku=%s AND external_product_id=%s
                  AND NULLIF(NULLIF(external_variation_id,''),'0') IS NOT DISTINCT FROM %s""",
                (event['provider'], event['site_key'], source['sku'], source['product_id'],
                 source['variation_id'])).fetchall()
            if rows != [(line['ecommerce_id'], line['erp_item_code'])]:
                raise OrderReview('item_mapping_review')

    def is_stale(self, event):
        with self.connect() as db:
            current = db.execute('''SELECT revision FROM public.mp_commerce_orders
                WHERE provider=%s AND site_key=%s AND external_order_id=%s''',
                tuple(event[key] for key in ('provider','site_key','external_order_id'))).fetchone()
        return current is not None and current[0] > event['revision']

    def link_erp(self,event,receipt):
        payload={k:event[k] for k in ('provider','site_key','external_order_id')}
        payload.update(erp_site=self.erp_site,sales_order=receipt['sales_order'],
                       sales_invoice=receipt.get('sales_invoice'),payment_entry=receipt.get('payment_entry'))
        with self.connect() as db:
            return db.execute('SELECT public.mp_commerce_link_erp(%s::jsonb)',(json.dumps(payload),)).fetchone()[0]


class ReviewedERP:
    """Transport adapter: order-specific commercial draft must be reviewed first."""
    def __init__(self,base,authorization,approved,request):
        from staging_origin import staging_origin
        self.base=staging_origin(base,'erp');self.authorization=authorization;self.approved=approved;self.request=request
    def draft_for(self, event):
        key = '|'.join(event[field] for field in ('provider', 'site_key', 'external_order_id'))
        draft = self.approved.get(key)
        if not isinstance(draft, dict):
            raise OrderReview('draft_review')
        return draft

    def __call__(self,event,mp_receipt):
        draft = self.draft_for(event)
        payload={'event':event,'reviewed_draft':draft}
        return self.request(self.base+'/api/method/rootedops_commerce.order_service.stage_order',
                            self.authorization,'POST',{'payload':json.dumps(payload)})['message']

    def resolve(self,event):
        identity={k:event[k] for k in ('provider','site_key','external_order_id')}
        return self.request(self.base+'/api/method/rootedops_commerce.order_service.resolve_order',
                            self.authorization,'POST',{'payload':json.dumps(identity)})['message']


def application(inbox,sites,customer_sites=None):
    """Loopback WSGI boundary; reverse-proxy deployment remains opt-in."""
    def app(environ,start_response):
        status='202 Accepted';result={}
        try:
            if environ.get('REQUEST_METHOD')!='POST':raise ValueError('method')
            if environ.get('wsgi.url_scheme')!='https' and environ.get('SERVER_NAME') not in ('127.0.0.1','localhost'):
                raise ValueError('transport')
            path=environ.get('PATH_INFO','').split('/')
            if len(path)!=4 or path[1]!='webhooks':raise ValueError('route')
            if path[2]=='woocommerce':
                receive, config = inbox.receive, sites[path[3]]
            elif path[2]=='woocommerce-customer':
                receive, config = inbox.receive_customer, (customer_sites or {})[path[3]]
            else:
                raise ValueError('route')
            size=int(environ.get('CONTENT_LENGTH',''))
            if not 0<size<=2*1024*1024:raise ValueError('size')
            if environ.get('CONTENT_TYPE','').split(';')[0]!='application/json':raise ValueError('content type')
            raw=environ['wsgi.input'].read(size)
            if len(raw)!=size:raise ValueError('truncated')
            result=receive(raw,environ.get('HTTP_X_WC_WEBHOOK_SIGNATURE',''),
                                 site=path[3],**config)
        except (ValueError,KeyError,TypeError):
            status='400 Bad Request';result={'error':'invalid_webhook'}
        except Exception:
            status='503 Service Unavailable';result={'error':'receipt_unavailable'}
        body=json.dumps(result).encode()
        start_response(status,[('Content-Type','application/json'),('Content-Length',str(len(body)))])
        return [body]
    return app
