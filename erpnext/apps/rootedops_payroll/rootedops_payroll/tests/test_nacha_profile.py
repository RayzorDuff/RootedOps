from unittest import TestCase

from rootedops_payroll.services.nacha_profile import (
    BALANCE_MODE_BALANCED,
    BALANCE_MODE_UNBALANCED,
    derive_company_identity,
    derive_nacha_company_id,
    normalize_ein,
    profile_readiness_errors,
    validate_immediate_destination,
    validate_odfi_identification,
)


class TestNachaCompanyIdentity(TestCase):
    def test_company_id_uses_erpnext_tax_id(self):
        self.assertEqual(derive_nacha_company_id("12-3456789"), "1123456789")

    def test_ein_requires_exactly_nine_digits(self):
        with self.assertRaises(ValueError):
            normalize_ein("12-345678")

    def test_high_plains_company_name_is_uppercase_and_batch_truncated(self):
        identity = derive_company_identity("Dank Mushrooms LLC", "12-3456789")
        self.assertEqual(identity.company_name, "DANK MUSHROOMS LLC")
        self.assertEqual(identity.batch_company_name, "DANK MUSHROOMS L")
        self.assertEqual(identity.company_id, "1123456789")


class TestNachaProfileValidation(TestCase):
    def _complete_profile(self):
        return {
            "funding_bank_account": "Dank Mushrooms Checking - High Plains Bank",
            "bank_name": "High Plains Bank",
            "immediate_destination": "102000021",
            "immediate_origin": "1123456789",
            "immediate_destination_name": "HIGH PLAINS BANK",
            "immediate_origin_name": "DANK MUSHROOMS LLC",
            "originating_dfi_identification": "10200002",
            "balance_mode": BALANCE_MODE_UNBALANCED,
            "reference_code": "",
        }

    def test_incomplete_profile_lists_unresolved_bank_fields(self):
        errors = profile_readiness_errors(
            {"balance_mode": "Unconfirmed"},
            company_name="Dank Mushrooms LLC",
            company_tax_id="12-3456789",
        )
        self.assertTrue(any("Immediate Destination" in error for error in errors))
        self.assertTrue(any("Balance Mode" in error for error in errors))

    def test_complete_unbalanced_profile_is_ready(self):
        errors = profile_readiness_errors(
            self._complete_profile(),
            company_name="Dank Mushrooms LLC",
            company_tax_id="12-3456789",
        )
        self.assertEqual(errors, [])

    def test_balanced_is_supported_as_a_confirmable_mode(self):
        profile = self._complete_profile()
        profile["balance_mode"] = BALANCE_MODE_BALANCED
        self.assertEqual(
            profile_readiness_errors(
                profile,
                company_name="Dank Mushrooms LLC",
                company_tax_id="12-3456789",
            ),
            [],
        )

    def test_destination_and_odfi_digit_lengths(self):
        self.assertEqual(validate_immediate_destination("102000021"), "102000021")
        self.assertEqual(validate_odfi_identification("10200002"), "10200002")
        with self.assertRaises(ValueError):
            validate_immediate_destination("10200002")
        with self.assertRaises(ValueError):
            validate_odfi_identification("102000021")
