import frappe
from frappe.model.document import Document


class CommerceOrderState(Document):
    def validate(self):
        old=self.get_doc_before_save()
        if any(self.get(f) and (not old or self.get(f)!=old.get(f)) for f in ('sales_invoice','payment_entry')):
            if not {'Accounts Manager','System Manager'} & set(frappe.get_roles()):
                frappe.throw('Accounts Manager required for financial links',frappe.PermissionError)
        if not old:return
        for field in ('source_key','provider','site_key','external_order_id','draft_hash'):
            if self.get(field)!=old.get(field):frappe.throw('Source identity and reviewed draft are immutable')
        for field in ('sales_order','sales_invoice','payment_entry'):
            if old.get(field) and self.get(field)!=old.get(field):frappe.throw('Document identity cannot be replaced')
        if any(self.get(f)!=old.get(f) for f in ('sales_invoice','payment_entry')):
            if not {'Accounts Manager','System Manager'} & set(frappe.get_roles()):
                frappe.throw('Accounts Manager required for financial links',frappe.PermissionError)
