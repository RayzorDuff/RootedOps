"""Create the Payroll Entry custom fields used by the RootedOps UI integration.

Load from bench console with the same pattern documented in README_SCRIPTS.md.
"""

from frappe.custom.doctype.custom_field.custom_field import create_custom_field


def ensure_payroll_entry_rootedops_fields():
    fields = [
        {
            "fieldname": "rootedops_consolidated_journal_entry",
            "label": "RootedOps Consolidated Journal Entry",
            "fieldtype": "Link",
            "options": "Journal Entry",
        },
        {
            "fieldname": "rootedops_salary_slip_count",
            "label": "RootedOps Salary Slip Count",
            "fieldtype": "Int",
            "read_only": 1,
        },
        {
            "fieldname": "rootedops_last_processed_on",
            "label": "RootedOps Last Processed On",
            "fieldtype": "Datetime",
            "read_only": 1,
        },
        {
            "fieldname": "rootedops_payroll_summary",
            "label": "RootedOps Payroll Summary",
            "fieldtype": "Long Text",
            "read_only": 1,
        },
    ]

    for df in fields:
        create_custom_field("Payroll Entry", df)

    print("Created / confirmed Payroll Entry custom fields.")
