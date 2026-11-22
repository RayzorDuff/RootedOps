# Move the existing WordPress site to dankmushrooms.net

This procedure is independent of the unmerged Woo order stack in PRs #111–#124.
Use the existing production Linode, WordPress installation and ERP site. Ecwid stays live.
Do not deploy the stacked hostname runbook's NGINX templates over the existing net vhost.

Owner evidence on November 21: both HTTPS My Account routes return 200, NGINX validates,
home is https://shop-test.danks.store, and siteurl is http://shop-test.danks.store.
Both WordPress settings will become **https://dankmushrooms.net**.

## What stays the same

- Compose project `dank-store-test`, database, volumes, users, numeric Woo IDs and ERP links.
- Customer integration logical site `shop-test.danks.store`, including private inbox JSON keys.
- Existing customer webhook destination and secret, with direct routing on shop-test.
- Ecwid routing, inventory publisher, open orders and reservations.

The only ERP configuration additions are `commerce_customer_sync.woo_origin` and the explicit
same-installation approval. Never search-replace customer identities, history, webhook options,
order records, GUIDs or private configuration. Do not redirect the old vhost wholesale.
There is no requirement for an order listener on port 8102 for this customer-only hostname mo…4935 tokens truncated…    set_primary(contact, 'phone_nos', 'phone', 'is_primary_phone', values['phone'])
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
