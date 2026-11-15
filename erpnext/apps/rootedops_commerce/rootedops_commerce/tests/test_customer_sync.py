"""Native Customer, Contact and Address lifecycle with mocked Woo transport."""
import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from rootedops_commerce import customer_sync as sync


class TestCustomerSync(IntegrationTestCase):
    def test_registration_address_edit_and_erp_projection(self):
        if not frappe.db.exists('Address Template', {'country': 'United States'}):
            frappe.get_doc(dict(doctype='Address Template', country='United States',
                                template='{{ address_line1 }}\n{{ city }}, {{ state }} {{ pincode }}')).insert()
        site = 'shop-test2.danks.store'
        customer_id = 912345
        config = {'customer_group': frappe.db.get_value('Customer Group', {'is_group': 0}),
                  'territory': frappe.db.get_value('Territory', {'is_group': 0})}
        remote = {'email': 'rootedops-customer-sync@example.invalid', 'first_name': 'Synthetic',
                  'last_name': 'Customer', 'billing': {}, 'shipping': {}}
        def request(site, customer_id, conf, body=None):
            if body:
                scope = body['scope']
                current_digest = sync.profile_digest(sync.woo_profile(remote, scope))
                if current_digest != body['expected_digest']:
                    raise sync.Review('both_changed')
                remote.update(body['values'] if scope == 'account' else {scope: body['values']})
            return remote
        def consume(scope, saved=None):
            values = sync.woo_profile(remote, 'account' if scope == 'registered' else scope)
            return sync.consume_signal(json.dumps(dict(site_key=site, id=customer_id, scope=scope,
                                        digest=sync.profile_digest(values if saved is None else saved))))
        with (patch.object(sync, 'settings', return_value=config),
              patch.object(sync, 'woo_request', side_effect=request) as woo):
            self.assertEqual(consume('registered')['status'], 'synced')
            self.assertEqual(consume('registered')['status'], 'synced')
            customer = sync.registered_customer(site, customer_id)
            self.assertEqual(frappe.db.count(sync.LINK, {'customer': customer}), 1)
            link = frappe.get_doc(sync.LINK, sync.link_key(site, customer_id))
            remote['billing'] = dict(address_1='1 Synthetic Street', city='Example', state='CO',
                                     postcode='80534', country='US', phone='9705550101')
            self.assertEqual(consume('billing')['status'], 'synced')
            self.assertEqual(consume('billing')['status'], 'synced')
            link.reload()
            address = frappe.get_doc('Address', link.billing_address)
            self.assertEqual(address.address_line1, '1 Synthetic Street')
            contact = frappe.get_doc('Contact', link.contact)
            self.assertEqual(contact.phone, '9705550101')
            contact.first_name = 'Changed'
            contact.save()
            woo.reset_mock()
            self.assertEqual(sync.project_profile(site, customer_id, 'account')['status'], 'synced')
            self.assertEqual(sync.project_profile(site, customer_id, 'account')['status'], 'unchanged')
            self.assertEqual(woo.call_count, 2)
            self.assertEqual(remote['first_name'], 'Changed')
            self.assertEqual(consume('account', saved=dict(email=remote['email'], first_name='Synthetic',
                             last_name='Customer'))['status'], 'stale')


            # Interleave a My Account change after the ERP read but before the
            # guarded write. Both edits survive and the baseline is unchanged.
            link.reload()
            baseline = link.account_digest
            contact.reload()
            contact.first_name = 'Second ERP edit'
            contact.save()

            def race(site, customer_id, conf, body=None):
                if body:
                    remote['first_name'] = 'Concurrent Woo edit'
                return request(site, customer_id, conf, body)

            woo.side_effect = race
            self.assertEqual(sync.project_profile(site, customer_id, 'account')['status'],
                             'review_both_changed')
            self.assertEqual(remote['first_name'], 'Concurrent Woo edit')
            self.assertEqual(frappe.db.get_value('Contact', contact.name, 'first_name'),
                             'Second ERP edit')
            link.reload()
            self.assertEqual(link.account_digest, baseline)
