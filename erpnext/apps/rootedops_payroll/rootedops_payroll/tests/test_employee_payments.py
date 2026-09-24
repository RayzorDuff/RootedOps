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
