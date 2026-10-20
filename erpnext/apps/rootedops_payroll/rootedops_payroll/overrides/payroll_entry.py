"""RootedOps Payroll Entry lifecycle integration.

RootedOps prepares and submits Salary Slips before the Payroll Entry itself.
Native HRMS Payroll Entry submission expects to create those slips itself,
so it otherwise treats the already-submitted slips as duplicates.

This extension requires a RootedOps consolidated Journal Entry or a fully
zero-value set of submitted Salary Slips. Other HRMS Payroll Entries retain
the native submission path.
"""

import frappe
from frappe import _


class RootedOpsPayrollEntryMixin:
    """Allow a prepared RootedOps Payroll Entry to adopt its Salary Slips."""

    def _rootedops_existing_submitted_salary_slips(self):
        employees = [
            row.employee
            for row in (self.get("employees") or [])
            if row.get("employee")
        ]
        employees = list(dict.fromkeys(employees))

        if not employees or not self.start_date or not self.end_date:
            return []

        return frappe.get_all(
            "Salary Slip",
            filters={
                "employee": ["in", employees],
                "start_date": self.start_date,
                "end_date": self.end_date,
                "docstatus": 1,
            },
            fields=["name", "employee", "company", "payroll_entry", "gross_pay", "net_pay"],
            order_by="creation asc",
        )

    def _rootedops_can_adopt_salary_slips(self):
        """Return True only for a complete RootedOps-prepared payroll."""
        employees = [
            row.employee
            for row in (self.get("employees") or [])
            if row.get("employee")
        ]
        employees = list(dict.fromkeys(employees))

        if not employees:
            return False

        slips = self._rootedops_existing_submitted_salary_slips()
        if len(slips) != len(employees):
            return False

        by_employee = {row.get("employee"): row for row in slips}
        if set(by_employee) != set(employees):
            return False

        for row in slips:
            if row.get("company") != self.company:
                return False
            if row.get("payroll_entry") and row.get("payroll_entry") != self.name:
                return False

        if self.get("rootedops_consolidated_journal_entry"):
            return True

        # A zero-dollar run produces no consolidated Journal Entry. Only
        # adopt when every selected employee has a submitted, zero-value slip.
        # A positive or negative payroll without a JE retains native validation.
        return all(
            abs(float(row.get("gross_pay") or 0)) < 0.005
            and abs(float(row.get("net_pay") or 0)) < 0.005
            for row in slips
        )

    def _rootedops_adopt_salary_slips(self):
        """Link the already-submitted Salary Slips to this Payroll Entry."""
        slips = self._rootedops_existing_submitted_salary_slips()

        for row in slips:
            if not row.get("payroll_entry"):
                frappe.db.set_value(
                    "Salary Slip",
                    row.get("name"),
                    "payroll_entry",
                    self.name,
                    update_modified=False,
                )

        self.db_set(
            {
                "salary_slips_created": 1,
                "salary_slips_submitted": 1,
            },
            update_modified=True,
        )

        return [row.get("name") for row in slips]

    def _rootedops_validate_payroll_payable_account(self):
        """Validate the configured payroll liability account without requiring Payable type."""
        account = self.get("payroll_payable_account")
        if not account:
            frappe.throw(_("Payroll Payable Account is required."))

        details = frappe.db.get_value(
            "Account",
            account,
            ["company", "is_group", "root_type"],
            as_dict=True,
        )
        if not details:
            frappe.throw(_("Payroll Payable Account {0} does not exist.").format(account))

        if details.company != self.company:
            frappe.throw(
                _("Payroll Payable Account {0} belongs to {1}, not {2}.").format(
                    account, details.company, self.company
                )
            )

        if details.is_group:
            frappe.throw(_("Payroll Payable Account {0} must be a ledger account, not a group account.").format(account))

        if details.root_type != "Liability":
            frappe.throw(
                _("Payroll Payable Account {0} must be a Liability account.").format(account)
            )

    def before_submit(self):
        if self._rootedops_can_adopt_salary_slips():
            self._rootedops_validate_payroll_payable_account()

            if self.get_employees_with_unmarked_attendance():
                frappe.throw(_("Cannot submit. Attendance is not marked for some employees."))

            return

        super().before_submit()

    def on_submit(self):
        if self._rootedops_can_adopt_salary_slips():
            self.set_status(update=True, status="Submitted")
            self._rootedops_adopt_salary_slips()
            return

        super().on_submit()
