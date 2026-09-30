"""RootedOps Payroll Entry lifecycle integration.

RootedOps prepares and submits Salary Slips before the Payroll Entry itself.
Native HRMS Payroll Entry submission expects to create those slips itself,
so it otherwise treats the already-submitted slips as duplicates.

This extension is deliberately gated on the RootedOps consolidated Journal Entry
link being present. That keeps ordinary HRMS Payroll Entries on the native
submission path.
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
            fields=["name", "employee", "company", "payroll_entry"],
            order_by="creation asc",
        )

    def _rootedops_can_adopt_salary_slips(self):
        """Return True only for a complete RootedOps-prepared payroll."""
        # The consolidated JE is created by the RootedOps payroll preparation
        # workflow and is not part of native HRMS Payroll Entry preparation.
        if not self.get("rootedops_consolidated_journal_entry"):
            return False

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

        return True

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

    def before_submit(self):
        if self._rootedops_can_adopt_salary_slips():
            self.validate_payroll_payable_account()

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
