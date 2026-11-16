import frappe
from frappe.model.document import Document


class CommerceCustomerLink(Document):
    def validate(self):
        previous = self.get_doc_before_save()
        previous_approval = previous.woo_review_approved if previous else 0
        if bool(self.woo_review_approved) != bool(previous_approval) and not self.flags.approving_signup_review:
            frappe.throw('Use the signup review action to approve this Woo link', frappe.PermissionError)
        if previous_approval:
            for field in ('site_key', 'woo_customer_id', 'customer', 'contact'):
                if self.get(field) != previous.get(field):
                    frappe.throw('The identity of an approved Woo link cannot be changed')
