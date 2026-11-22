import base64
import csv
from dataclasses import dataclass
import hmac
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'integrations/commerce'))
sys.path.insert(0, str(ROOT / 'erpnext/apps/rootedops_commerce'))

from customer_review import compile_new_customers, review, write_csv, ADDRESS_FIELDS
from customer_signals import ACTION, deliver_customer, normalize_signal, PROVIDER, request_erp_customer
from inbox import application, same_receipt
from orders import normalize_woo

SITE = 'shop-test2.danks.store'
SECRET = 'synthetic-customer-webhook-secret-only'


def signed(action=ACTION):
    body = {'action': action, 'arg': {'id': 12, 'scope': 'account',
            'event': 'a23c14be-23ad-4b5a-97c2-fdf7944ed25b', 'digest': 'b' * 64}}
    raw = json.dumps(body).encode()
    return raw, base64.b64encode(hmac.digest(SECRET.encode(), raw, 'sha256')).decode()


class CustomerSignals(unittest.TestCase):
    def test_woo_action_topic_and_legacy_deliveries(self):
        plugin = (ROOT / 'wordpress/dank-mu-plugins/rootedops-customer-webhook.php').read_text()
        self.assertTrue(ACTION.startswith(('woocommerce_', 'wc_')))
        self.assertIn(f"do_action( '{ACTION}',", plugin)
        raw, signature = signed('rootedops_customer_profile_saved')
        self.assertEqual(normalize_signal(raw, signature, [SECRET], SITE)['id'], 12)
        raw, signature = signed('woocommerce_unrelated_action')
        with self.assertRaises(ValueError):
            normalize_signal(raw, signature, [SECRET], SITE)

    def test_raw_signature_and_routing(self):
        raw, signature = signed()
        with self.assertRaises(ValueError):
            normalize_signal(raw + b' ', signature, [SECRET], SITE)
        event = normalize_signal(raw, signature, [SECRET], SITE)
        self.assertEqual((event['provider'], event['id'], event['scope']), (PROVIDER, 12, 'account'))
        self.assertEqual(event, normalize_signal(raw, signature, [SECRET], SITE))
        inbox = Mock()
        inbox.receive_customer.return_value = {'duplicate': False}
        app = application(inbox, {}, {SITE: {'secrets': [SECRET]}})
        replies = []
        env = dict(REQUEST_METHOD='POST', SERVER_NAME='127.0.0.1', PATH_INFO='/webhooks/' + PROVIDER + '/' + SITE,
                   CONTENT_LENGTH=str(len(raw)), CONTENT_TYPE='application/json',
                   HTTP_X_WC_WEBHOOK_SIGNATURE=signature)
        app(dict(env, **{'wsgi.input': io.BytesIO(raw)}), lambda status, headers: replies.append(status))
        self.assertEqual(replies, ['202 Accepted'])
        inbox.receive_customer.assert_called_once_with(raw, signature, site=SITE, secrets=[SECRET])
        inbox.receive.assert_not_called()

    @patch('customer_signals.subprocess.run')
    def test_customer_curl_keeps_credentials_in_stdin_and_rejects_http_errors(self, run):
        token = 'token synthetic-key:synthetic-secret'
        url = 'https://erp.danks.store/api/method/rootedops_commerce.customer_sync.consume_signal'
        run.return_value = SimpleNamespace(returncode=0, stdout='{"message":{"status":"synced"}}\n200')
        result = request_erp_customer(url, token, 'POST', {'payload': '{}'})
        self.assertEqual(result['message']['status'], 'synced')
        args, options = run.call_args
        self.assertNotIn(token, ' '.join(args[0]))
        self.assertIn(token, options['input'])
        self.assertNotIn('--location', args[0])

        run.return_value.stdout = 'private response body\n403'
        with patch('sys.stderr', new_callable=io.StringIO) as stderr, self.assertRaises(RuntimeError):
            request_erp_customer(url, token, 'POST', {'payload': '{}'})
        self.assertEqual(stderr.getvalue(), 'ERP customer request: HTTP 403\n')

    def test_customer_worker_does_not_apply_inventory_and_resumes_erp_receipt(self):
        raw, signature = signed()
        event = normalize_signal(raw, signature, [SECRET], SITE)
        claim = {'payload': event, 'erp_receipt': {'status': 'synced'}}
        inbox = Mock()
        inbox.claim.return_value = claim
        request = Mock()
        self.assertTrue(deliver_customer(inbox, 'https://erp-test2.danks.store', 'test', request, site=SITE))
        inbox.claim.assert_called_once_with(provider=PROVIDER, site=SITE, lease_seconds=300)
        request.assert_not_called()
        inbox.record.assert_called_once_with(claim, 'mp', {'status': 'not_applicable'})
        inbox.finish.assert_called_once_with(claim)

    def test_order_intake_separates_registered_customer_and_guest(self):
        order = {'id': 11, 'status': 'pending', 'currency': 'USD', 'total': '10.00',
                 'date_modified_gmt': '2026-11-15T12:00:00', 'payment_method': 'clover',
                 'line_items': [{'id': 1, 'product_id': 2, 'sku': 'SYNTHETIC', 'quantity': 1}],
                 'billing': {'address_1': 'Order snapshot'}}
        def normalized():
            raw = json.dumps(order).encode()
            signature = base64.b64encode(hmac.digest(SECRET.encode(), raw, 'sha256')).decode()
            return normalize_woo(raw, signature, [SECRET], SITE,
                {'2': {'sku': 'SYNTHETIC', 'erp_item_code': 'SYNTHETIC', 'ecommerce_id': 3}}, {'clover': 'clover'})
        order['customer_id'] = 12
        registered = normalized()
        self.assertEqual(registered['external_customer_id'], '12')
        self.assertNotIn('billing', registered)
        legacy = {key: val for key, val in registered.items() if key != 'external_customer_id'}
        self.assertTrue(same_receipt(legacy, registered))
        order['customer_id'] = 0
        self.assertIsNone(normalized()['external_customer_id'])
        order['customer_id'] = True
        with self.assertRaises(ValueError):
            normalized()


@dataclass
class Link:
    customer: str = 'ERP-TEST'
    account_digest: str = ''
    account_status: str = 'synced'

    def get(self, field):
        return getattr(self, field, None)

    def set(self, field, value):
        setattr(self, field, value)

    def save(self):
        pass


class ProfileSync(unittest.TestCase):
    def test_hostname_transport_preserves_existing_identity(self):
        conf = dict(woo_site='shop-test.danks.store', same_woo_installation=True,
                    production_erp_pilot=True, woo_origin='https://dankmushrooms.net',
                    woo_authorization='Basic synthetic')
        reply = Mock()
        reply.__enter__ = Mock()
        reply.__exit__ = Mock(return_value=False)
        with patch.multiple(self.sync.frappe, create=True,
                            local=SimpleNamespace(site='erp.danks.store')):
            key = self.sync.link_key('shop-test.danks.store', 12)
            for body, suffix in ((None, '?context=edit'), ({'synthetic': True}, '/rootedops-projection')):
                reply.__enter__.return_value = io.StringIO('{"id":12,"role":"customer"}')
                with patch.object(self.sync, 'build_opener') as opener:
                    opener.return_value.open.return_value = reply
                    self.sync.woo_request('shop-test.danks.store', '12', conf, body)
                    request = opener.return_value.open.call_args.args[0]
                    self.assertEqual(request.full_url, 'https://dankmushrooms.net/wp-json/wc/v3/customers/12' + suffix)
                    self.assertEqual(request.get_method(), 'GET' if body is None else 'PUT')
                    self.assertEqual(request.get_header('User-agent'), 'RootedOps-Commerce/1.0')
                    self.assertEqual(request.get_header('Authorization'), conf['woo_authorization'])
                self.assertEqual(self.sync.link_key(conf['woo_site'], 12), key)
            for origin in ('https://evil.invalid', 'http://dankmushrooms.net', 'https://dankmushrooms.net@evil.invalid'):
                with patch.dict(conf, woo_origin=origin), self.assertRaises(ValueError):
                    self.sync.woo_request('shop-test.danks.store', '12', conf)
            with patch.dict(conf, same_woo_installation=False), self.assertRaises(ValueError):
                self.sync.woo_request('shop-test.danks.store', '12', conf)
            with self.assertRaises(ValueError):
                self.sync.woo_request('shop-test2.danks.store', '12', conf)

    def test_shared_api_identifies_reads_and_writes_to_cloudflare(self):
        from ecwid_migrate import api
        for method, payload in (('GET', None), ('PUT', {'synthetic': True})):
            with self.subTest(method=method), patch('urllib.request.build_opener') as opener:
                response = opener.return_value.open.return_value
                response.__enter__.return_value = io.StringIO('{"id":12}')
                self.assertEqual(api('https://dankmushrooms.net/wp-json/wc/v3/customers/12',
                                     'Basic synthetic', method, payload), {'id': 12})
                request = opener.return_value.open.call_args.args[0]
                self.assertEqual(request.get_header('User-agent'), 'RootedOps-Commerce/1.0')
                self.assertEqual(request.get_header('Authorization'), 'Basic synthetic')
                self.assertEqual(request.get_method(), method)

    @classmethod
    def setUpClass(cls):
        fake = SimpleNamespace(whitelist=lambda **kw: lambda f: f, parse_json=json.loads)
        with patch.dict(sys.modules, {'frappe': fake}):
            from rootedops_commerce import customer_sync
        cls.sync = customer_sync

    def setUp(self):
        self.base = {'first_name': 'Test', 'last_name': 'Profile', 'email': 'test@example.invalid'}
        self.new = dict(self.base, first_name='Updated')
        self.link = Link(account_digest=self.sync.profile_digest(self.base))

    def signal(self, values):
        return json.dumps(dict(site_key=SITE, id=12, scope='account', digest=self.sync.profile_digest(values)))

    def test_production_pilot_requires_exact_pair_and_valid_configured_ids(self):
        conf = {'enabled': True, 'woo_site': 'shop-test.danks.store',
                'production_erp_pilot': True, 'woo_customer_ids': [12]}
        with patch.multiple(self.sync.frappe, create=True,
                            conf={'commerce_customer_sync': conf},
                            local=SimpleNamespace(site='erp.danks.store'),
                            get_roles=lambda: ['Sales Manager']):
            self.assertIs(self.sync.settings('shop-test.danks.store'), conf)
            with self.assertRaises(ValueError):
                self.sync.settings('shop-test2.danks.store')
            with patch.dict(conf, woo_customer_ids=["invalid"]), self.assertRaises(ValueError):
                self.sync.settings('shop-test.danks.store')
            with patch.dict(conf, production_erp_pilot=False), self.assertRaises(ValueError):
                self.sync.settings('shop-test.danks.store')

    def test_production_pilot_does_not_create_a_link_for_account_edits(self):
        conf = {'production_erp_pilot': True, 'woo_customer_ids': [13]}
        with (patch.object(self.sync, 'settings', return_value=conf),
              patch.object(self.sync, 'lock_link', return_value=None) as lock,
              patch.object(self.sync, 'woo_request') as woo):
            signal = self.signal(self.new)
            self.assertEqual(self.sync.consume_signal(signal)['status'],
                             'ignored_unapproved_customer')
            lock.assert_called_once_with(SITE, '12', create=False)
            lock.reset_mock()
            conf['woo_customer_ids'] = [12]
            self.assertEqual(self.sync.consume_signal(signal)['status'], 'review_link_required')
            lock.assert_called_once_with(SITE, '12', create=False)
            woo.assert_not_called()

    def test_production_signup_defaults_are_required_without_an_allowlist(self):
        conf = {'enabled': True, 'woo_site': 'shop-test.danks.store', 'production_erp_pilot': True,
                'provision_new_woo_customers': True, 'customer_group': 'Individual',
                'territory': 'United States'}
        db = SimpleNamespace(get_value=lambda doctype, name, field: 0 if name else None)
        with patch.multiple(self.sync.frappe, create=True, db=db,
                            conf={'commerce_customer_sync': conf},
                            local=SimpleNamespace(site='erp.danks.store'),
                            get_roles=lambda: ['Sales Manager']):
            self.assertIs(self.sync.settings('shop-test.danks.store'), conf)
            with patch.dict(conf, territory=''), self.assertRaisesRegex(ValueError, 'Territory'):
                self.sync.settings('shop-test.danks.store')
            with patch.dict(conf, provision_new_woo_customers=False):
                self.assertIs(self.sync.settings('shop-test.danks.store'), conf)

    def test_ui_approved_link_syncs_without_a_file_allowlist_or_automatic_signup(self):
        conf = {'production_erp_pilot': True, 'woo_customer_ids': []}
        self.link.woo_review_approved = 1
        with (patch.object(self.sync, 'settings', return_value=conf),
              patch.object(self.sync, 'lock_link', return_value=self.link),
              patch.object(self.sync, 'woo_request', return_value=self.new),
              patch.object(self.sync, 'erp_profile', side_effect=[self.base, self.new]),
              patch.object(self.sync, 'write_erp') as write):
            self.assertEqual(self.sync.consume_signal(self.signal(self.new))['status'], 'synced')
            write.assert_called_once_with(self.link, 'account', self.new)

    def test_production_signup_creates_once_and_existing_email_goes_to_review(self):
        conf = {'production_erp_pilot': True, 'provision_new_woo_customers': True}
        self.link.customer = None
        self.link.woo_signup_provisioned = 0
        signup = json.loads(self.signal(self.base))
        signup['scope'] = 'registered'

        def create(link, profile, config):
            link.customer = 'CUSTOMER-TEST'

        with (patch.object(self.sync, 'settings', return_value=conf),
              patch.object(self.sync, 'lock_link', return_value=self.link) as lock,
              patch.object(self.sync, 'woo_request', return_value=self.new) as woo,
              patch.object(self.sync, 'create_customer', side_effect=create) as provision,
              patch.object(self.sync, 'erp_profile', return_value=self.new)):
            self.assertEqual(self.sync.consume_signal(self.signal(self.new))['status'],
                             'review_link_required')
            lock.assert_called_once_with(SITE, '12', create=False)
            woo.assert_not_called()
            self.assertEqual(self.sync.consume_signal(json.dumps(signup))['status'], 'synced')
            self.assertEqual(self.link.woo_signup_provisioned, 1)
            provision.assert_called_once_with(self.link, self.new, conf)
            self.assertEqual(self.sync.consume_signal(json.dumps(signup))['status'], 'already_linked')
            self.assertEqual(self.sync.consume_signal(self.signal(self.new))['status'], 'synced')
            self.assertEqual(provision.call_count, 1)

            self.link.customer = None
            self.link.woo_signup_provisioned = 0
            provision.side_effect = self.sync.Review('erp_email_match')
            self.assertEqual(self.sync.consume_signal(json.dumps(signup))['status'],
                             'review_erp_email_match')
            self.assertIsNone(self.link.customer)
            self.assertEqual(self.link.woo_signup_provisioned, 0)

    def test_woo_edit_applies_once_and_stale_body_does_not_revert(self):
        with (patch.object(self.sync, 'settings', return_value={}),
              patch.object(self.sync, 'lock_link', return_value=self.link),
              patch.object(self.sync, 'woo_request', return_value=self.new),
              patch.object(self.sync, 'erp_profile', side_effect=[self.base, self.new, self.new]),
              patch.object(self.sync, 'write_erp') as write):
            self.assertEqual(self.sync.consume_signal(self.signal(self.new))['status'], 'synced')
            self.assertEqual(self.sync.consume_signal(self.signal(self.new))['status'], 'synced')
            self.assertEqual(self.sync.consume_signal(self.signal(self.base))['status'], 'stale')
            write.assert_called_once_with(self.link, 'account', self.new)

    def test_conflicting_and_replayed_projection(self):
        self.link.contact = 'CONTACT-TEST'
        with (patch.object(self.sync, 'settings', return_value={}),
              patch.object(self.sync, 'lock_link', return_value=self.link),
              patch.object(self.sync, 'erp_profile', return_value=self.new),
              patch.object(self.sync, 'matching_contacts', return_value=set()),
              patch.object(self.sync, 'woo_request', side_effect=[
                  dict(self.base, first_name='Other'), self.base, self.new, self.new]) as woo):
            self.assertEqual(self.sync.project_profile(SITE, 12, 'account')['status'], 'review_both_changed')
            self.assertEqual(self.sync.project_profile(SITE, 12, 'account')['status'], 'synced')
            self.assertEqual(self.sync.project_profile(SITE, 12, 'account')['status'], 'unchanged')
            self.assertEqual(woo.call_count, 4)
            self.assertEqual(woo.call_args_list[-2].args[-1], {
                'scope': 'account', 'expected_digest': self.sync.profile_digest(self.base),
                'values': self.new,
            })

    def test_projection_detects_woo_drift_when_erp_matches_baseline(self):
        with (patch.object(self.sync, 'settings', return_value={}),
              patch.object(self.sync, 'lock_link', return_value=self.link),
              patch.object(self.sync, 'erp_profile', return_value=self.base),
              patch.object(self.sync, 'woo_request', return_value=self.new) as woo):
            self.assertEqual(self.sync.project_profile(SITE, 12, 'account')['status'], 'review_woo_changed')
            woo.assert_called_once_with(SITE, '12', {})
            self.assertEqual(self.link.account_digest, self.sync.profile_digest(self.base))

    def test_production_scheduler_queues_only_approved_linked_accounts(self):
        conf = {'enabled': True, 'project_enabled': True, 'production_erp_pilot': True,
                'provision_new_woo_customers': True, 'woo_customer_ids': [12], 'woo_site': SITE}
        links = [
            Link(), Link(), Link(), Link(),
        ]
        for i, link in enumerate(links, start=12):
            link.name = f'link-{i}'
            link.woo_customer_id = str(i)
            link.woo_review_approved = i == 13
            link.woo_signup_provisioned = i == 14
        enqueue = Mock()
        get_all = Mock(return_value=links)
        with (patch.multiple(self.sync.frappe, create=True,
                             conf={'commerce_customer_sync': conf}, get_all=get_all, enqueue=enqueue),
              patch.object(self.sync, 'settings', return_value=conf)):
            self.sync.queue_projections()
            self.assertEqual(enqueue.call_count, 9)
            self.assertEqual({c.kwargs['customer_id'] for c in enqueue.call_args_list}, {'12', '13', '14'})
            self.assertTrue(all(c.args[0] == self.sync.project_changed_profile for c in enqueue.call_args_list))
            self.assertEqual(get_all.call_args.kwargs['filters']['customer'], ['is', 'set'])
            enqueue.reset_mock()
            conf['project_enabled'] = False
            self.sync.queue_projections()
            enqueue.assert_not_called()

    def test_scheduled_projection_checks_opt_in_and_skips_unchanged_erp_profiles(self):
        config = {'project_enabled': True}
        with (patch.object(self.sync, 'settings', return_value=config),
              patch.object(self.sync, 'lock_link', return_value=self.link) as lock,
              patch.object(self.sync, 'erp_profile', return_value=self.base),
              patch.object(self.sync, 'woo_request') as woo):
            self.assertEqual(self.sync.project_changed_profile(SITE, 12, 'account')['status'], 'unchanged')
            woo.assert_not_called()
            lock.reset_mock()
            config['project_enabled'] = False
            self.assertEqual(self.sync.project_changed_profile(SITE, 12, 'account')['status'], 'disabled')
            lock.assert_not_called()

    def test_projection_http_precondition_failure_keeps_baseline(self):
        self.link.contact = 'CONTACT-TEST'
        remote = dict(self.base, id=12, role='customer')
        initial_digest = self.link.account_digest
        response = io.BytesIO(json.dumps(remote).encode())
        guarded_route = f'https://{SITE}/wp-json/wc/v3/customers/12/rootedops-projection'
        conflict = HTTPError(guarded_route, 412, 'Precondition Failed', None, None)
        with (patch.object(self.sync, 'settings', return_value={'woo_authorization': 'synthetic'}),
              patch.object(self.sync, 'lock_link', return_value=self.link),
              patch.object(self.sync, 'erp_profile', return_value=self.new),
              patch.object(self.sync, 'matching_contacts', return_value=set()),
              patch.object(self.sync, 'build_opener') as opener):
            opener.return_value.open.side_effect = [response, conflict]
            self.assertEqual(self.sync.project_profile(SITE, 12, 'account')['status'],
                             'review_both_changed')
            self.assertEqual(self.link.account_digest, initial_digest)
            calls = opener.return_value.open.call_args_list
            self.assertEqual(len(calls), 2)
            guarded_request = calls[-1].args[0]
            self.assertEqual(guarded_request.full_url, guarded_route)
            self.assertEqual(guarded_request.get_method(), 'PUT')
            self.assertEqual(json.loads(guarded_request.data), {
                'scope': 'account', 'expected_digest': initial_digest, 'values': self.new,
            })


class CustomerReview(unittest.TestCase):
    def test_history_details_require_explicit_approval_and_never_replay_orders(self):
        with tempfile.TemporaryDirectory() as temp:
            customer, orders, reviewed = [Path(temp) / (name + '.csv') for name in ('customer','orders','review')]
            customer.write_text('email;name;registered;accept marketing\nsample@example.invalid;Sample Person;date;false\n')
            order_fields = ['order_number', 'email', 'timestamp', 'payment_status_code', 'fulfillment_status_code']
            order_fields.extend(prefix + field for prefix in ('shipto_person_', 'bill_person_') for field in ADDRESS_FIELDS)
            row = dict(order_number='100', email='sample@example.invalid', timestamp='Nov 15, 2026 01:00 PM',
                       payment_status_code='PAID', fulfillment_status_code='DELIVERED',
                       shipto_person_street_1='1 Sample Street', shipto_person_city='Example',
                       shipto_person_country_code='US', shipto_person_phone='555-0100')
            with orders.open('w', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=order_fields, delimiter=';')
                writer.writeheader()
                writer.writerow(row)
                writer.writerow(row)
                writer.writerow(dict(row, order_number='101', email=''))
            rows, summary = review(customer, orders, store_id='10',
                                   source_customers=[dict(id=42, email='sample@example.invalid')])
            self.assertEqual(summary['orders_without_email'], 1)
            self.assertEqual(summary['shipping_address_candidates'], 1)
            self.assertEqual(rows[0]['ecwid_id_candidate'], '42')
            self.assertEqual(rows[0]['ecwid_customer_id'], '')
            rows[0].update(decision='create_erp', ecwid_customer_id='42', approved_contact_order='100')
            write_csv(reviewed, rows)
            plan = compile_new_customers(reviewed, store_id='10', customer_group='Retail', territory='US')
            self.assertEqual(plan['orders'], [])
            self.assertFalse(plan['financial_replay'])
            self.assertEqual(plan['customers'][0]['addresses'][0]['address_type'], 'Shipping')
            self.assertEqual(plan['customers'][0]['contact']['phone_nos'][0]['phone'], '555-0100')
