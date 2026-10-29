from frappe.model.document import Document

import hashlib
import json
import frappe

class CommerceSourceArchive(Document):
    def validate(self):
        canonical = json.dumps(json.loads(self.payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        self.payload_hash = hashlib.sha256(canonical.encode()).hexdigest()
        if not self.is_new() and self.has_value_changed("payload"):
            frappe.throw("Source archives are immutable; use a versioned source key")
