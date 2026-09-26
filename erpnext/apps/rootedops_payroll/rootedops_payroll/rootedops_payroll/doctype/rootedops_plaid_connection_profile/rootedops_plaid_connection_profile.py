from frappe.model.document import Document


class RootedOpsPlaidConnectionProfile(Document):
    """One independent Plaid credential context.

    Raw Plaid credentials are intentionally not stored in this DocType. The
    profile stores references to protected configuration keys instead.
    """

    def validate(self):
        from rootedops_payroll.services.plaid_profile import validate_profile_document

        validate_profile_document(self)
