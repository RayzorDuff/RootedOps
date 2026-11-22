"""Durable external business identity, stored with its ERP effect."""
import hashlib
import json

import frappe

DOCTYPE = 'Commerce External Receipt'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def lock_receipt(scope, identity, payload):
    key = hashlib.sha256(canonical([scope, identity])).hexdigest()
    digest = hashlib.sha256(canonical(payload)).hexdigest()
    if frappe.db.exists(DOCTYPE, key):
        record = frappe.get_doc(DOCTYPE, key, for_update=True)
        record.check_permission('read')
        if record.fingerprint != digest or not record.result:
            raise ValueError('External identity requires reconciliation')
    else:
        record = frappe.get_doc(dict(doctype=DOCTYPE, receipt_key=key, fingerprint=digest)).insert()
    return record


def finish(record, result):
    record.result = canonical(result).decode()
    record.save()
    return result
