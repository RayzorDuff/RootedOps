import unittest
from unittest.mock import patch

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
