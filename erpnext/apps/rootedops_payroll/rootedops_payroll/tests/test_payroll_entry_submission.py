import unittest
from unittest.mock import patch

from rootedops_payroll.api.payroll_entry_actions import (
    _refresh_draft_consolidated_journal_entry,
)
from rootedops_payroll.overrides.payroll_entry import RootedOpsPayrollEntryMixin


class FakeEmployee:
    def __init__(self, employee):
        self.employee = employee


class FakePayrollEntry(RootedOpsPayrollEntryMixin):
    company = "Dank Mushrooms, LLC"
    start_date = "2026-09-21"
    end_date = "2026-09-27"
    name = "HR-PRUN-2026-00057"

    def __init__(self, employees, consolidated_je, slips):
        self.employees = [FakeEmployee(employee) for employee in employees]
        self.rootedops_consolidated_journal_entry = consolidated_je
        self._slips = slips

    def get(self, fieldname, default=None):
        return getattr(self, fieldname, default)


class TestRootedOpsPayrollEntryMixin(unittest.TestCase):
    def _assert_adoption(self, slips, consolidated_je, expected):
        pe = FakePayrollEntry(
            ["HR-EMP-00005", "HR-EMP-00008", "HR-EMP-00009"],
            consolidated_je,
            slips,
        )
        with patch(
            "rootedops_payroll.overrides.payroll_entry.frappe.get_all",
            return_value=slips,
        ):
            self.assertEqual(pe._rootedops_can_adopt_salary_slips(), expected)

    def test_complete_rootedops_result_can_be_adopted(self):
        slips = [
            {"name": "Sal Slip/HR-EMP-00005/00030", "employee": "HR-EMP-00005",
             "company": "Dank Mushrooms, LLC", "payroll_entry": None},
            {"name": "Sal Slip/HR-EMP-00008/00003", "employee": "HR-EMP-00008",
             "company": "Dank Mushrooms, LLC", "payroll_entry": None},
            {"name": "Sal Slip/HR-EMP-00009/00001", "employee": "HR-EMP-00009",
             "company": "Dank Mushrooms, LLC", "payroll_entry": None},
        ]
        self._assert_adoption(slips, "ACC-JV-2026-00418", True)

    def test_refresh_draft_consolidated_journal_entry_updates_existing_draft(self):
        class FakeJournalEntry:
            name = "ACC-JV-2026-00418"
            docstatus = 0
            company = "Dank Mushrooms, LLC"
            voucher_type = "Journal Entry"

            def __init__(self):
                self.accounts = []
                self.posting_date = None
                self.user_remark = None
                self.saved = False

            def set(self, fieldname, value):
                setattr(self, fieldname, value)

            def save(self, ignore_permissions=False):
                self.saved = ignore_permissions

        je = FakeJournalEntry()
        preview = {
            "posting_date": "2026-09-27",
            "company": "Dank Mushrooms, LLC",
            "voucher_type": "Journal Entry",
            "user_remark": "Consolidated payroll accrual for Dank Mushrooms, LLC 2026-09-21 to 2026-09-27 (3 salary slips)",
            "accounts": [
                {"account": "Payroll Expense - DML", "debit_in_account_currency": 416.30, "credit_in_account_currency": 0.0},
                {"account": "Payroll Payable - DML", "debit_in_account_currency": 0.0, "credit_in_account_currency": 372.27},
            ],
            "total_debit": 460.83,
            "total_credit": 460.83,
            "is_balanced": True,
        }

        with patch(
            "rootedops_payroll.api.payroll_entry_actions.frappe.get_doc",
            return_value=je,
        ), patch(
            "rootedops_payroll.api.payroll_entry_actions.frappe.db.commit"
        ):
            result = _refresh_draft_consolidated_journal_entry(
                "ACC-JV-2026-00418",
                preview,
            )

        self.assertTrue(result["refreshed"])
        self.assertEqual(je.accounts, preview["accounts"])
        self.assertEqual(je.posting_date, "2026-09-27")
        self.assertIn("(3 salary slips)", je.user_remark)
        self.assertTrue(je.saved)

    def test_refresh_draft_consolidated_journal_entry_rejects_submitted_je(self):
        class FakeJournalEntry:
            docstatus = 1
            company = "Dank Mushrooms, LLC"
            voucher_type = "Journal Entry"

        with patch(
            "rootedops_payroll.api.payroll_entry_actions.frappe.get_doc",
            return_value=FakeJournalEntry(),
        ):
            with self.assertRaises(Exception):
                _refresh_draft_consolidated_journal_entry(
                    "ACC-JV-2026-00418",
                    {"company": "Dank Mushrooms, LLC", "voucher_type": "Journal Entry"},
                )

    def test_no_rootedops_marker_uses_native_path(self):
        slips = [
            {"name": "Sal Slip/HR-EMP-00005/00030", "employee": "HR-EMP-00005",
             "company": "Dank Mushrooms, LLC", "payroll_entry": None},
            {"name": "Sal Slip/HR-EMP-00008/00003", "employee": "HR-EMP-00008",
             "company": "Dank Mushrooms, LLC", "payroll_entry": None},
            {"name": "Sal Slip/HR-EMP-00009/00001", "employee": "HR-EMP-00009",
             "company": "Dank Mushrooms, LLC", "payroll_entry": None},
        ]
        self._assert_adoption(slips, None, False)

    def test_partial_result_does_not_bypass_native_validation(self):
        slips = [
            {"name": "Sal Slip/HR-EMP-00005/00030", "employee": "HR-EMP-00005",
             "company": "Dank Mushrooms, LLC", "payroll_entry": None},
        ]
        self._assert_adoption(slips, "ACC-JV-2026-00418", False)

    def test_wrong_company_does_not_bypass_native_validation(self):
        slips = [
            {"name": "Sal Slip/HR-EMP-00005/00030", "employee": "HR-EMP-00005",
             "company": "Other Company", "payroll_entry": None},
            {"name": "Sal Slip/HR-EMP-00008/00003", "employee": "HR-EMP-00008",
             "company": "Dank Mushrooms, LLC", "payroll_entry": None},
            {"name": "Sal Slip/HR-EMP-00009/00001", "employee": "HR-EMP-00009",
             "company": "Dank Mushrooms, LLC", "payroll_entry": None},
        ]
        self._assert_adoption(slips, "ACC-JV-2026-00418", False)

    def test_different_payroll_entry_does_not_bypass_native_validation(self):
        slips = [
            {"name": "Sal Slip/HR-EMP-00005/00030", "employee": "HR-EMP-00005",
             "company": "Dank Mushrooms, LLC", "payroll_entry": "HR-PRUN-2026-00056"},
            {"name": "Sal Slip/HR-EMP-00008/00003", "employee": "HR-EMP-00008",
             "company": "Dank Mushrooms, LLC", "payroll_entry": "HR-PRUN-2026-00056"},
            {"name": "Sal Slip/HR-EMP-00009/00001", "employee": "HR-EMP-00009",
             "company": "Dank Mushrooms, LLC", "payroll_entry": "HR-PRUN-2026-00056"},
        ]
        self._assert_adoption(slips, "ACC-JV-2026-00418", False)


if __name__ == "__main__":
    unittest.main()
