from frappe.model.document import Document

from rootedops_commerce.contract import mapping_key

class CommerceChannelMapping(Document):
    def autoname(self):
        self.name = mapping_key(self.provider, self.site_key, self.external_product_id, self.external_variation_id)

    def validate(self):
        expected = mapping_key(self.provider, self.site_key, self.external_product_id, self.external_variation_id)
        if self.name and not self.is_new() and self.name != expected:
            import frappe
            frappe.throw("Channel identity is immutable; create a new mapping")
