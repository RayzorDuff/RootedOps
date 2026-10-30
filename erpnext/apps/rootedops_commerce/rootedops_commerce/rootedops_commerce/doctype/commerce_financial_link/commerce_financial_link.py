import frappe
from frappe.model.document import Document


class CommerceFinancialLink(Document):
    def validate(self):
        if not self.is_new():
            frappe.throw("Financial source links are immutable")
