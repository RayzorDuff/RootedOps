from rootedops_payroll.services.payroll_engine import ensure_employee_tax_profile_custom_fields
from rootedops_payroll.services.tax_compliance import ensure_tax_payment_custom_fields


def after_migrate():
    ensure_employee_tax_profile_custom_fields()
    ensure_tax_payment_custom_fields()
