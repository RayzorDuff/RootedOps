from frappe.model.document import Document

import frappe

class CommercialProductContent(Document):
    def validate(self):
        seen = set()
        for row in self.channel_overrides:
            key = (row.provider.strip().lower(), row.site_key.strip())
            if key in seen:
                frappe.throw("Duplicate provider/site override")
            seen.add(key)
            row.provider, row.site_key = key
