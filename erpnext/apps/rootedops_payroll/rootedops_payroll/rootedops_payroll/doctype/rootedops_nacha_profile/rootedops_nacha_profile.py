from frappe.model.document import Document

from rootedops_payroll.services.nacha_profile import validate_and_project_profile


class RootedOpsNACHAProfile(Document):
    def validate(self):
        validate_and_project_profile(self)
