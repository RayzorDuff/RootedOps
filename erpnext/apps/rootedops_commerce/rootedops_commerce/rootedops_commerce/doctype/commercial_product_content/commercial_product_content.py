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

    def on_update(self):
        """Keep native Item display fields in sync when canonical content is edited.

        No reverse sync from Item, and no Woo publish side effects. Refuse to
        overwrite independently edited Item values instead of guessing priority.
        """
        previous = self.get_doc_before_save()
        if previous is None:
            return
        title_changed = self.public_title != previous.public_title
        description_changed = (self.full_description or "") != (previous.full_description or "")
        if not (title_changed or description_changed):
            return
        item = frappe.get_doc("Item", self.item)
        item.check_permission("write")
        if title_changed:
            if (item.item_name or "") not in (previous.public_title or "", self.public_title or ""):
                frappe.throw("Native Item title drift: reconcile before editing commercial title")
            item.item_name = self.public_title
        if description_changed:
            if (item.description or "") not in (previous.full_description or "", self.full_description or ""):
                frappe.throw("Native Item description drift: reconcile before editing commercial content")
            item.description = self.full_description or ""
        item.save()
