import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

SALARY_SLIP_CUSTOM_FIELDS = {
    "Salary Slip": [
        {
            "fieldname": "rootedops_payroll_details_section",
            "label": "RootedOps Payroll Details",
            "fieldtype": "Section Break",
            "insert_after": "payment_days",
        },
        {
            "fieldname": "total_working_hours",
            "label": "Total Working Hours",
            "fieldtype": "Float",
            "read_only": 1,
            "print_hide": 0,
            "precision": "2",
            "insert_after": "rootedops_payroll_details_section",
        },
    ]
}

create_custom_fields(SALARY_SLIP_CUSTOM_FIELDS, update=True)
frappe.db.commit()
print("Created/updated Salary Slip custom field: total_working_hours")
