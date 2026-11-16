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
            self.assertEqual(woo.call_count, 3)
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

    def test_production_signup_rejects_duplicate_erp_email_and_provisions_new_email(self):
        site = 'shop-test.danks.store'
        config = {
            'production_erp_pilot': True,
            'provision_new_woo_customers': True,
            'customer_group': frappe.db.get_value('Customer Group', {'is_group': 0}),
            'territory': frappe.db.get_value('Territory', {'is_group': 0}),
        }
        duplicate = 'existing-signup-contact@example.invalid'
        email = 'new-production-signup@example.invalid'
        frappe.get_doc(dict(doctype='Contact', first_name='Existing',
                            email_ids=[dict(email_id=duplicate, is_primary=1)])).insert()

        def register(customer_id, address):
            profile = dict(email=address, first_name='', last_name='')
            signal = dict(site_key=site, id=customer_id, scope='registered',
                          digest=sync.profile_digest(profile))
            with patch.object(sync, 'woo_request', return_value=profile):
                return sync.consume_signal(json.dumps(signal))['status']

        with patch.object(sync, 'settings', return_value=config):
            self.assertEqual(register(912346, duplicate), 'review_erp_email_match')
            review = frappe.get_doc(sync.LINK, sync.link_key(site, 912346))
            self.assertFalse(review.customer)
            self.assertFalse(review.woo_signup_provisioned)
            self.assertEqual(register(912347, email), 'synced')
            self.assertEqual(register(912347, email), 'already_linked')
            link = frappe.get_doc(sync.LINK, sync.link_key(site, 912347))
            self.assertTrue(link.woo_signup_provisioned)
            self.assertEqual(frappe.get_doc('Contact', link.contact).email_id, email)
            self.assertEqual(frappe.db.count('Contact Email', {'email_id': email}), 1)
            original_contact = link.contact
            self.assertEqual(frappe.db.get_value('Contact', original_contact, 'full_name'),
                             'Woo customer #912347')
            self.assertEqual(sync.erp_profile(link, 'account')['first_name'], '')

            from rootedops_commerce.patches.repair_woo_contact_names import execute

            frappe.db.set_value('Contact', original_contact,
                                {'first_name': link.source_key, 'full_name': link.source_key})
            frappe.db.set_value(sync.LINK, link.name, 'woo_contact_name_placeholder', 0)
            execute()
            execute()
            link.reload()
            self.assertEqual(link.contact, original_contact)
            self.assertEqual(frappe.db.get_value('Contact', original_contact, 'full_name'),
                             'Woo customer #912347')
            self.assertEqual(sync.erp_profile(link, 'account')['first_name'], '')

    def test_system_manager_can_approve_an_existing_signup_review(self):
        site = 'shop-test.danks.store'
        customer_id = 912348
        config = {'production_erp_pilot': True, 'provision_new_woo_customers': True}
        account = dict(email='approval-example@example.invalid', first_name='Reviewed',
                       last_name='Shopper', billing={}, shipping={})
        customer = frappe.get_doc(dict(doctype='Customer', customer_type='Individual',
                                      customer_name='Reviewed Woo Shopper',
                                      customer_group=frappe.db.get_value('Customer Group', {'is_group': 0}),
                                      territory=frappe.db.get_value('Territory', {'is_group': 0}))).insert()
        contact = frappe.get_doc(dict(
            doctype='Contact', first_name=account['first_name'], last_name=account['last_name'],
            email_ids=[dict(email_id=account['email'], is_primary=1)],
            links=[dict(link_doctype='Customer', link_name=customer.name)],
        )).insert()
        key = sync.link_key(site, customer_id)
        with (patch.object(sync, 'settings', return_value=config),
              patch.object(sync, 'woo_request', return_value=account)):
            signal = dict(site_key=site, id=customer_id, scope='registered',
                          digest=sync.profile_digest(sync.woo_profile(account, 'account')))
            self.assertEqual(sync.consume_signal(json.dumps(signal))['status'], 'review_erp_email_match')
            with patch.object(frappe, 'get_roles', return_value=['Sales Manager']):
                with self.assertRaises(frappe.PermissionError):
                    sync.approve_signup_review(key, customer.name, contact.name)

            self.assertEqual(sync.get_signup_review(key), sync.woo_profile(account, 'account'))
            self.assertEqual(sync.approve_signup_review(key, customer.name, contact.name)['status'], 'linked')
            link = frappe.get_doc(sync.LINK, key)
            self.assertEqual(link.customer, customer.name)
            self.assertEqual(link.contact, contact.name)
            self.assertTrue(link.woo_review_approved)
            self.assertFalse(link.woo_signup_provisioned)
            self.assertEqual(link.account_status, 'synced')
