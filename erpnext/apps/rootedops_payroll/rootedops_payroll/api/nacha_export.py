import frappe

from rootedops_payroll.services.nacha_export import generate_payroll_nacha_file


@frappe.whitelist()
def generate_payroll_nacha(payroll_entry_name: str, profile_name: str, effective_date: str):
    """Generate and validate a payroll NACHA file, returning the download payload and audit metadata."""
    return generate_payroll_nacha_file(payroll_entry_name, profile_name, effective_date)
