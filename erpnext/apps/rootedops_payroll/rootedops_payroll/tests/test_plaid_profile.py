from unittest import TestCase
from unittest.mock import MagicMock, patch

from rootedops_payroll.services.plaid_profile import (
    PlaidProfileError,
    get_plaid_profile_status,
    plaid_base_url,
    validate_profile_name,
)


class TestPlaidProfileFoundation(TestCase):
    def test_profile_name_is_generic_and_stable(self):
        self.assertEqual(validate_profile_name("business"), "business")
        self.assertEqual(validate_profile_name("rental_property_2"), "rental_property_2")

    def test_profile_name_rejects_environment_specific_punctuation(self):
        with self.assertRaises(PlaidProfileError):
            validate_profile_name("Personal Profile")

    def test_supported_environment_urls(self):
        self.assertEqual(plaid_base_url("sandbox"), "https://sandbox.plaid.com")
        self.assertEqual(plaid_base_url("development"), "https://development.plaid.com")
        self.assertEqual(plaid_base_url("production"), "https://production.plaid.com")

    def test_unsupported_environment_rejected(self):
        with self.assertRaises(PlaidProfileError):
            plaid_base_url("test")

    @patch("rootedops_payroll.services.plaid_profile.frappe.get_doc")
    @patch("rootedops_payroll.services.plaid_profile._config_value")
    def test_status_never_returns_credentials(self, config_value, get_doc):
        get_doc.return_value = MagicMock(
            name="business",
            display_name="Business",
            enabled=1,
            is_default=1,
            environment="production",
            client_id_secret_ref="PLAID_BUSINESS_CLIENT_ID",
            secret_secret_ref="PLAID_BUSINESS_SECRET",
        )
        config_value.side_effect = lambda ref: "SECRET-VALUE" if ref else None

        status = get_plaid_profile_status("business")

        self.assertTrue(status["credentials_resolvable"])
        self.assertNotIn("client_id", status)
        self.assertNotIn("secret", status)
        self.assertNotIn("SECRET-VALUE", str(status))
