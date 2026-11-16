"""Explicit Woo account edits and reviewed ERP canonical customer projection."""
import hashlib
import json
import re
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener

import frappe

from rootedops_commerce.contract import mapping_key

LINK = 'Commerce Customer Link'
SCOPES = {
    'account': ('email', 'first_name', 'last_name'),
    'billing': ('address_1', 'address_2', 'city', 'state', 'postcode', 'country', 'phone'),
    'shipping': ('address_1', 'address_2', 'city', 'state', 'postcode', 'country'),
}
ADDRESS = {'address_1': 'address_line1', 'address_2': 'address_line2', 'city': 'city',
           'state': 'state', 'postcode': 'pincode'}


class Review(Exception):
    """An identity or profile needs operator review."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def settings(site):
    conf = frappe.conf.get('commerce_customer_sync') or {}
    allowed = {'erp-test.danks.store': 'shop-test.danks.store',
               'erp-test2.danks.store': 'shop-test2.danks.store'}
    pilot = conf.get('production_erp_pilot') is True
    if pilot:
        paired = frappe.local.site == 'erp.danks.store' and site == 'shop-test.danks.store'
        ids = conf.get('woo_customer_ids', [])
        if (not isinstance(ids, list)
                or any(not re.fullmatch(r'[1-9][0-9]{0,18}', str(value)) for value in ids)):
            raise ValueError('Configure reviewed Woo customer IDs for the production ERP pilot')
    else:
        paired = allowed.get(frappe.local.site) == site
    if not conf.get('enabled') or not paired or conf.get('woo_site') != site:
        raise ValueError('Customer synchronization is disabled for this site pair')
    if not {'System Manager', 'Sales Manager'} & set(frappe.get_roles()):
        frappe.throw('Commerce role required', frappe.PermissionError)
    if signup_provisioning(conf):
        for key, doctype in (('customer_group', 'Customer Group'), ('territory', 'Territory')):
            name = conf.get(key)
            if not name or frappe.db.get_value(doctype, name, 'is_group') != 0:
                raise ValueError(f'Select an existing leaf {doctype} for Woo signups')
    return conf


def signup_provisioning(conf):
    return (conf.get('production_erp_pilot') is True
            and conf.get('provision_new_woo_customers') is True)


def pilot_customer_allowed(conf, customer_id):
    return (conf.get('production_erp_pilot') is not True
            or str(customer_id) in {str(value) for value in conf.get('woo_customer_ids', [])})


def profile_digest(profile):
    encoded = json.dumps(profile, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    return hashlib.sha256(encoded.encode()).hexdigest()


def woo_profile(doc, scope):
    values = doc if scope == 'account' else doc[scope]
    return {key: str(values.get(key) or '').strip(' \t\n\r\0\v') for key in SCOPES[scope]}


def woo_request(site, customer_id, conf, body=None):
    path = f'https://{site}/wp-json/wc/v3/customers/{customer_id}'
    path += '?context=edit' if body is None else '/rootedops-projection'
    req = Request(path, data=None if body is None else json.dumps(body).encode(),
                  method='GET' if body is None else 'PUT',
                  headers={'Authorization': conf['woo_authorization'], 'Content-Type': 'application/json'})
    try:
        with build_opener(NoRedirect).open(req, timeout=12) as response:
            account = json.load(response)
    except HTTPError as error:
        if body is not None and error.code == 412:
            raise Review('both_changed') from None
        if error.code in (400, 404, 409):
            raise Review('woo_identity_or_profile') from None
        raise RuntimeError('Woo customer endpoint unavailable') from None
    if str(account.get('id')) != customer_id or account.get('role') != 'customer':
        raise Review('woo_identity_or_profile')
    return account


def link_key(site, customer_id):
    if not re.fullmatch(r'[1-9][0-9]{0,18}', str(customer_id)):
        raise ValueError('Stable Woo customer ID required')
    return mapping_key('woocommerce', site, str(customer_id))


def lock_link(site, customer_id, create=False):
    key = link_key(site, customer_id)
    if frappe.db.exists(LINK, key):
        link = frappe.get_doc(LINK, key, for_update=True)
        link.check_permission('write')
        return link
    if create:
        return frappe.get_doc(dict(doctype=LINK, source_key=key, site_key=site,
                                    woo_customer_id=str(customer_id))).insert()
    return None


def linked_doc(link, field, doctype):
    name = link.get(field)
    if not name:
        return None
    doc = frappe.get_doc(doctype, name, for_update=True)
    doc.check_permission('read')
    if doc.is_new() or {(r.link_doctype, r.link_name) for r in doc.links} != {('Customer', link.customer)}:
        raise Review('shared_or_missing_erp_record')
    return doc


def primary(rows, field, flag):
    selected = [r.get(field) for r in rows if r.get(flag)]
    if len(selected) > 1 or (field == 'email_id' and rows and not selected):
        raise Review('ambiguous_erp_primary')
    return selected[0] if selected else ''


def contact_name_placeholder(link):
    return f'Woo customer #{link.woo_customer_id}'


def apply_contact_name(link, contact, values):
    first_name, last_name = values['first_name'], values['last_name']
    needs_placeholder = not (first_name or last_name)
    link.woo_contact_name_placeholder = int(needs_placeholder)
    contact.first_name = contact_name_placeholder(link) if needs_placeholder else first_name
    contact.last_name = last_name


def erp_profile(link, scope):
    contact = linked_doc(link, 'contact', 'Contact')
    if scope == 'account':
        if not contact:
            raise Review('missing_erp_contact')
        email = primary(contact.email_ids, 'email_id', 'is_primary')
        first_name = contact.first_name or ''
        if first_name == link.source_key or (
                link.get('woo_contact_name_placeholder') and first_name == contact_name_placeholder(link)):
            first_name = ''
        return woo_profile(dict(email=email, first_name=first_name, last_name=contact.last_name), scope)
    address = linked_doc(link, scope + '_address', 'Address')
    values = {key: (address.get(field) or '') if address else '' for key, field in ADDRESS.items()}
    values['country'] = (frappe.db.get_value('Country', address.country, 'code') or '').upper() if address else ''
    if address and not values['country']:
        raise Review('unknown_country_code')
    if scope == 'billing':
        values['phone'] = primary(contact.phone_nos, 'phone', 'is_primary_phone') if contact else ''
    return woo_profile({scope: values}, scope)


def set_primary(doc, table, field, flag, value):
    old = primary(doc.get(table), field, flag)
    if old == value:
        return
    replacement = next((row for row in doc.get(table) if row.get(field) == value), None)
    for row in list(doc.get(table)):
        if row.get(flag):
            if not value and table == 'phone_nos' and not row.is_primary_mobile_no:
                doc.remove(row)
            else:
                row.set(flag, 0)
    if replacement:
        replacement.set(flag, 1)
    elif value:
        doc.append(table, {field: value, flag: 1})


def matching_contacts(email):
    return set(frappe.get_all('Contact Email', filters={'email_id': email}, pluck='parent'))


def validate_inbound(link, scope, values):
    if scope == 'account':
        if not frappe.utils.validate_email_address(values['email']) or len(values['email']) > 140:
            raise Review('invalid_account_email')
        if (matching_contacts(values['email']) - {link.contact}
                or set(frappe.get_all('Customer', filters={'email_id': values['email']}, pluck='name')) - {link.customer}):
            raise Review('erp_email_match')
        return None
    fields = [values[key] for key in (*ADDRESS, 'country')]
    if not any(fields):
        if link.get(scope + '_address'):
            raise Review('address_removal_needs_review')
        return None
    if not all(values[key] for key in ('address_1', 'city', 'country')):
        raise Review('incomplete_address')
    countries = frappe.get_all('Country', filters={'code': values['country'].lower()}, pluck='name')
    if len(countries) != 1:
        raise Review('unknown_country_code')
    return countries[0]


def write_erp(link, scope, values):
    country = validate_inbound(link, scope, values)
    contact = linked_doc(link, 'contact', 'Contact')
    if scope == 'account':
        apply_contact_name(link, contact, values)
        set_primary(contact, 'email_ids', 'email_id', 'is_primary', values['email'])
        contact.save()
        return
    if country:
        address = linked_doc(link, scope + '_address', 'Address')
        if not address:
            address = frappe.get_doc(dict(doctype='Address', address_title=link.customer,
                                          address_type=scope.title(),
                                          links=[dict(link_doctype='Customer', link_name=link.customer)]))
        address.update({field: values[key] for key, field in ADDRESS.items()})
        address.country = country
        address.save()
        link.set(scope + '_address', address.name)
    if scope == 'billing':
        set_primary(contact, 'phone_nos', 'phone', 'is_primary_phone', values['phone'])
        contact.save()


def status(link, scope, result, digest=None):
    if link:
        status_field = scope + '_status'
        digest_field = scope + '_digest'
        if link.get(status_field) != result or (digest is not None and link.get(digest_field) != digest):
            link.set(status_field, result)
            if digest is not None:
                link.set(digest_field, digest)
            link.save()
    return {'status': result}


def create_customer(link, profile, conf):
    validate_inbound(link, 'account', profile)
    name = ' '.join(profile[key] for key in ('first_name', 'last_name') if profile[key]) or profile['email']
    customer = frappe.get_doc(dict(doctype='Customer', customer_name=name, customer_type='Individual',
                                  customer_group=conf['customer_group'], territory=conf['territory'])).insert()
    contact = frappe.get_doc(dict(doctype='Contact',
                                  email_ids=[dict(email_id=profile['email'], is_primary=1)],
                                  links=[dict(link_doctype='Customer', link_name=customer.name)]))
    apply_contact_name(link, contact, profile)
    contact.insert()
    link.customer, link.contact = customer.name, contact.name
    link.save()


@frappe.whitelist(methods=['POST'])
def consume_signal(payload):
    signal = frappe.parse_json(payload)
    site, customer_id = signal['site_key'], str(signal['id'])
    conf = settings(site)
    registered = signal['scope'] == 'registered'
    scope = 'account' if registered else signal['scope']
    if scope not in SCOPES:
        raise ValueError('Unknown profile scope')
    approved = pilot_customer_allowed(conf, customer_id)
    provision = signup_provisioning(conf)
    pilot = conf.get('production_erp_pilot') is True
    signup = provision and registered
    link = lock_link(site, customer_id, create=signup or (not pilot and scope == 'account'))
    new_signup = signup and not link.customer
    reviewed = link and link.get('woo_review_approved')
    if not approved and not provision and not reviewed:
        return {'status': 'ignored_unapproved_customer'}
    managed = reviewed or (provision and link and link.woo_signup_provisioned)
    if pilot and not new_signup and (not (approved or managed) or not link or not link.customer):
        return {'status': 'review_link_required'}
    if signup and link.customer:
        return {'status': 'already_linked'}
    if not link or (not link.customer and scope != 'account'):
        return {'status': 'awaiting_registration'}
    try:
        values = woo_profile(woo_request(site, customer_id, conf), scope)
        digest = profile_digest(values)
        # A signup authorizes provisioning this Woo ID. Use its verified current
        # profile if the account was edited before the worker received the signup.
        if not new_signup and digest != signal['digest']:
            # The saved fields have changed since the signed account action.
            # Preserve the last actionable status on the crosswalk.
            return {'status': 'stale'}
        if not link.customer:
            create_customer(link, values, conf)
            if new_signup:
                link.woo_signup_provisioned = 1
            blank = {key: '' for key in SCOPES['shipping']}
            link.shipping_digest = profile_digest(blank)
            link.billing_digest = profile_digest(dict(blank, phone=''))
        else:
            erp_digest = profile_digest(erp_profile(link, scope))
            if digest != erp_digest:
                if erp_digest != link.get(scope + '_digest'):
                    return status(link, scope, 'review_both_changed')
                write_erp(link, scope, values)
                if profile_digest(erp_profile(link, scope)) != digest:
                    raise ValueError('ERP did not retain the approved profile')
        return status(link, scope, 'synced', digest)
    except Review as exc:
        return status(link, scope, 'review_' + str(exc))


@frappe.whitelist(methods=['POST'])
def link_existing(payload):
    """Bind explicitly reviewed ERP records to a stable, existing Woo account."""
    data = frappe.parse_json(payload)
    site, customer_id = data['site_key'], str(data['id'])
    conf = settings(site)
    if not pilot_customer_allowed(conf, customer_id):
        raise ValueError('Woo customer has not been approved for the production ERP pilot')
    link = lock_link(site, customer_id, create=True)
    return bind_existing(link, data, conf)


def signup_review(name, for_update=False):
    if 'System Manager' not in frappe.get_roles():
        frappe.throw('System Manager role required to approve a Woo signup', frappe.PermissionError)
    link = frappe.get_doc(LINK, name, for_update=for_update)
    link.check_permission('write')
    conf = settings(link.site_key)
    if link.name != link_key(link.site_key, link.woo_customer_id):
        frappe.throw('Invalid Woo customer review identity')
    if link.customer or link.account_status != 'review_erp_email_match':
        frappe.throw('This Woo signup is no longer waiting for email-match review')
    return link, conf


@frappe.whitelist(methods=['GET'])
def get_signup_review(name):
    link, conf = signup_review(name)
    return woo_profile(woo_request(link.site_key, str(link.woo_customer_id), conf), 'account')


@frappe.whitelist(methods=['POST'])
def approve_signup_review(name, customer, contact, billing_address=None, shipping_address=None):
    link, conf = signup_review(name, for_update=True)
    data = dict(customer=customer, contact=contact, billing_address=billing_address,
                shipping_address=shipping_address, ecwid_identity=link.ecwid_identity)
    return bind_existing(link, data, conf, reviewed=True)


def bind_existing(link, data, conf, reviewed=False):
    site, customer_id = link.site_key, str(link.woo_customer_id)
    fields = ('customer', 'contact', 'billing_address', 'shipping_address', 'ecwid_identity')
    if link.customer:
        if any((link.get(field) or '') != (data.get(field) or '') for field in fields):
            raise ValueError('Existing link differs from reviewed mapping')
        return {'status': 'linked'}
    for field in fields:
        link.set(field, data.get(field))
    customer = frappe.get_doc('Customer', link.customer, for_update=True)
    customer.check_permission('read')
    # One account per ERP customer and store. Serialize review by Customer.
    if frappe.db.exists(LINK, {'site_key': site, 'customer': customer.name, 'name': ['!=', link.name]}):
        raise ValueError('ERP Customer already linked to another account in this store')
    if link.ecwid_identity:
        previous = frappe.get_doc('Commerce Migration Identity', link.ecwid_identity)
        previous.check_permission('read')
        if previous.target_doctype != 'Customer' or previous.target_name != customer.name:
            raise ValueError('Ecwid migration identity targets a different Customer')
    if link.billing_address and link.billing_address == link.shipping_address:
        raise ValueError('Use distinct account address records for billing and shipping')
    woo = woo_request(site, customer_id, conf)
    for scope in SCOPES:
        try:
            erp = erp_profile(link, scope)
        except Review as error:
            if reviewed:
                frappe.throw(f'Cannot link {scope}: {str(error).replace("_", " ")}')
            raise
        remote = woo_profile(woo, scope)
        if erp != remote:
            if reviewed:
                frappe.throw(f'The Woo and ERP {scope} fields must agree before linking')
            raise ValueError('Reconcile the reviewed ERP and Woo profiles before linking')
        link.set(scope + '_digest', profile_digest(erp))
        link.set(scope + '_status', 'synced')
    if reviewed:
        link.flags.approving_signup_review = True
        link.woo_review_approved = 1
    link.save()
    return {'status': 'linked'}


def registered_customer(site, customer_id):
    link = frappe.get_doc(LINK, link_key(site, customer_id))
    link.check_permission('read')
    if not link.customer:
        raise ValueError('Registered Woo order needs a resolved customer link')
    return link.customer


def projection_allowed(conf, link, customer_id):
    return (pilot_customer_allowed(conf, customer_id)
            or bool(link and (link.get('woo_review_approved')
                             or (signup_provisioning(conf) and link.woo_signup_provisioned))))


@frappe.whitelist(methods=['POST'])
def project_profile(site, customer_id, scope):
    return project_scope(site, customer_id, scope)


def project_changed_profile(site, customer_id, scope):
    return project_scope(site, customer_id, scope, automatic=True)


def project_scope(site, customer_id, scope, automatic=False):
    conf = settings(site)
    if automatic and not conf.get('project_enabled'):
        return {'status': 'disabled'}
    if scope not in SCOPES:
        raise ValueError('Unknown profile scope')
    link = lock_link(site, customer_id)
    if not projection_allowed(conf, link, customer_id):
        return {'status': 'ignored_unapproved_customer'}
    if not link or not link.customer:
        return {'status': 'unlinked'}
    try:
        values = erp_profile(link, scope)
        digest = profile_digest(values)
        baseline = link.get(scope + '_digest')
        if automatic and digest == baseline:
            return {'status': 'unchanged'}
        remote = woo_profile(woo_request(site, str(customer_id), conf), scope)
        remote_digest = profile_digest(remote)
        if digest == remote_digest:
            status(link, scope, 'synced', digest)
            return {'status': 'unchanged' if digest == baseline else 'synced'}
        if digest == baseline:
            return status(link, scope, 'review_woo_changed')
        if remote_digest != baseline:
            return status(link, scope, 'review_both_changed')
        if scope == 'account' and (not values['email'] or matching_contacts(values['email']) - {link.contact}):
            return status(link, scope, 'review_erp_email_match')
        body = {'scope': scope, 'expected_digest': remote_digest, 'values': values}
        if woo_profile(woo_request(site, str(customer_id), conf, body), scope) != values:
            raise ValueError('Woo did not retain the projected profile')
        return status(link, scope, 'synced', digest)
    except Review as exc:
        return status(link, scope, 'review_' + str(exc))


def queue_projections():
    conf = frappe.conf.get('commerce_customer_sync') or {}
    if not conf.get('enabled') or not conf.get('project_enabled'):
        return
    site = conf.get('woo_site')
    conf = settings(site)
    links = frappe.get_all(LINK, filters={'site_key': site, 'customer': ['is', 'set']},
                           fields=['name', 'woo_customer_id', 'woo_review_approved', 'woo_signup_provisioned'])
    for link in links:
        if not projection_allowed(conf, link, link.woo_customer_id):
            continue
        for scope in SCOPES:
            frappe.enqueue(project_changed_profile, site=site, customer_id=link.woo_customer_id, scope=scope,
                           job_id=f'commerce-customer-{link.name}-{scope}', deduplicate=True, timeout=90)
