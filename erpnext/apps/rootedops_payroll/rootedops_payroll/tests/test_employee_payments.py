from unittest import TestCase
from unittest.mock import patch

from rootedops_payroll.services.employee_payments import (
    PAYMENT_METHODS,
    payment_configuration_is_effective,
    validate_payment_method,
)


class TestEmployeePaymentConfiguration(TestCase):
    def test_expected_payment_methods_are_supported(self):
        self.assertEqual(
            PAYMENT_METHODS,
            (
                "ACH",
                "Venmo",
                "Apple Pay / Apple Cash",
                "Paper Check",
                "Other / Manual",
            ),
        )

    def test_active_configuration_without_effective_date_is_effective(self):
        self.assertTrue(
            payment_configuration_is_effective(
                {
                    "active": 1,
                    "payment_method": "ACH",
                    "effective_date": None,
                },
                "2026-09-24",
            )
        )

    def test_future_configuration_is_not_yet_effective(self):
        self.assertFalse(
            payment_configuration_is_effective(
                {
                    "active": 1,
                    "payment_method": "Venmo",
                    "effective_date": "2026-10-01",
                },
                "2026-09-24",
            )
        )

    def test_inactive_configuration_is_not_effective(self):
        self.assertFalse(
            payment_configuration_is_effective(
                {
                    "active": 0,
                    "payment_method": "Paper Check",
                    "effective_date": None,
                },
                "2026-09-24",
            )
        )

    def test_blank_method_is_allowed_until_configuration_is_activated(self):
        self.assertIsNone(validate_payment_method(None))

    @patch("rootedops_payroll.services.employee_payments.frappe.throw")
    def test_unknown_method_is_rejected(self, frappe_throw):
        frappe_throw.side_effect = ValueError("unsupported")
        with self.assertRaises(ValueError):
            validate_payment_method("Cash App")


class TestEmployeePaymentDraftFoundation(TestCase):
    def test_payment_key_is_stable_per_salary_slip(self):
        from rootedops_payroll.services.employee_payments import build_employee_payment_key

        self.assertEqual(
            build_employee_payment_key("SAL-SLIP-2026-00042"),
            "salary-slip:SAL-SLIP-2026-00042:full-net-pay",
        )

    @patch("rootedops_payroll.services.employee_payments._employee_payment_journal_entry_doc")
    @patch("rootedops_payroll.services.employee_payments.preflight_employee_payroll_payments")
    def test_create_drafts_creates_one_je_per_preflight_plan(self, preflight, build_doc):
        from types import SimpleNamespace
        from rootedops_payroll.services.employee_payments import create_employee_payroll_payment_drafts

        preflight.return_value = {
            "plans": [
                {
                    "employee": "HR-EMP-00001",
                    "employee_name": "Employee A",
                    "salary_slip": "SAL-001",
                    "payment_method": "Venmo",
                    "net_pay": 350.00,
                },
                {
                    "employee": "HR-EMP-00002",
                    "employee_name": "Employee B",
                    "salary_slip": "SAL-002",
                    "payment_method": "ACH",
                    "net_pay": 425.00,
                },
            ],
            "zero_net_pay_salary_slips": [],
            "checking_bank_account": "Checking - DML",
            "total_net_pay": 775.00,
        }
        docs = [
            SimpleNamespace(name="ACC-JV-001", docstatus=0, insert=lambda **kwargs: None),
            SimpleNamespace(name="ACC-JV-002", docstatus=0, insert=lambda **kwargs: None),
        ]
        build_doc.side_effect = docs

        result = create_employee_payroll_payment_drafts(
            [{"slip_name": "SAL-001"}, {"slip_name": "SAL-002"}],
            payroll_entry="HR-PRUN-001",
            company="Dank Mushrooms, LLC",
            posting_date="2026-09-24",
        )

        self.assertEqual(result["employee_count"], 2)
        self.assertEqual(result["total_net_pay"], 775.00)
        self.assertEqual(
            [row["journal_entry"] for row in result["journal_entries"]],
            ["ACC-JV-001", "ACC-JV-002"],
        )
        self.assertEqual(build_doc.call_count, 2)
