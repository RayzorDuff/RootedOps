from frappe.model.document import Document


class RootedOpsIntegrationEvent(Document):
    """Durable idempotency/audit record for one external business event."""

    pass
