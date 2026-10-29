from frappe.model.document import Document

import hashlib
import json
import frappe

class CommerceSourceArchive(Document):
    def validate(self):
        canonical = json.dumps(json.loads(self.payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        self.payload_hash = hashlib.sha256(canonical.encode()).hexdigest()
        if not self.is_new() and any(self.has_value_changed(field) for field in ("payload", "source_key", "record_type")):
            frappe.throw("Source archives are immutable; use a versioned source key")
