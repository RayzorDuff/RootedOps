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


class TestLegacyPlaidProfileBootstrap(TestCase):
    @patch("rootedops_payroll.services.plaid_profile.frappe.db.exists", return_value=False)
    @patch("rootedops_payroll.services.plaid_profile.frappe.get_single")
    @patch("rootedops_payroll.services.plaid_profile.frappe.get_doc")
    def test_bootstrap_uses_legacy_settings_references(self, get_doc, get_single, exists):
        from rootedops_payroll.services.plaid_profile import (
            LEGACY_PLAID_CLIENT_ID_REF,
            LEGACY_PLAID_SECRET_REF,
            bootstrap_legacy_plaid_profile,
        )

        settings = MagicMock(plaid_client_id="client-id", plaid_env="production")
        settings.get_password.return_value = "secret"
        get_single.return_value = settings
        doc = MagicMock(name="business")
        get_doc.return_value = doc

        result = bootstrap_legacy_plaid_profile()

        self.assertEqual(result, {"created": True, "profile": doc.name})
        payload = get_doc.call_args.args[0]
        self.assertEqual(payload["client_id_secret_ref"], LEGACY_PLAID_CLIENT_ID_REF)
        self.assertEqual(payload["secret_secret_ref"], LEGACY_PLAID_SECRET_REF)
        self.assertEqual(payload["environment"], "production")
        self.assertNotIn("client-id", payload.values())
        self.assertNotIn("secret", payload.values())
