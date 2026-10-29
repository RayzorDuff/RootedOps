"""Durable immutable source-to-ERP identity. No financial side effects."""
import frappe
from frappe.model.document import Document


class CommerceMigrationIdentity(Document):
    def validate(self):
        if not self.is_new():
            frappe.throw("Migration identities are immutable; reconcile through a reviewed migration")
