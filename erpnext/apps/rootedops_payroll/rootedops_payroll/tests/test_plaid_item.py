from unittest import TestCase

from rootedops_payroll.services.plaid_item import (
    PLAID_ACCESS_TOKEN_FIELD,
    PLAID_ITEM_DOCTYPE,
    PLAID_PROFILE_FIELD,
    PlaidItemProfileError,
    verify_plaid_item_migration,
)


class TestPlaidItemProfileBinding(TestCase):
    def test_constants_bind_to_erpnext_bank_representation(self):
        self.assertEqual(PLAID_ITEM_DOCTYPE, "Bank")
        self.assertEqual(PLAID_ACCESS_TOKEN_FIELD, "plaid_access_token")
        self.assertEqual(PLAID_PROFILE_FIELD, "plaid_profile")

    def test_migration_verification_accepts_profile_only_change(self):
        before = {
            "item_count": 2,
            "items": {
                "Business Checking": {"profile": None, "state_fingerprint": "a"},
                "Business Savings": {"profile": "business", "state_fingerprint": "b"},
            },
            "bank_account_counts": {"Business Checking": 1, "Business Savings": 1},
            "bank_transaction_counts": {
                "Business Checking": {"Bank Account 1": 10},
                "Business Savings": {"Bank Account 2": 20},
            },
        }
        after = {
            "item_count": 2,
            "items": {
                "Business Checking": {"profile": "business", "state_fingerprint": "a"},
                "Business Savings": {"profile": "business", "state_fingerprint": "b"},
            },
            "bank_account_counts": before["bank_account_counts"],
            "bank_transaction_counts": before["bank_transaction_counts"],
        }

        result = verify_plaid_item_migration(before, after)

        self.assertTrue(result["ok"])
        self.assertEqual(result["item_count"], 2)
        self.assertEqual(result["profiled_item_count"], 2)
        self.assertEqual(result["errors"], [])

    def test_migration_verification_rejects_item_state_change(self):
        before = {
            "item_count": 1,
            "items": {"Checking": {"profile": None, "state_fingerprint": "original"}},
            "bank_account_counts": {"Checking": 1},
            "bank_transaction_counts": {"Checking": {"Bank Account": 5}},
        }
        after = {
            "item_count": 1,
            "items": {"Checking": {"profile": "business", "state_fingerprint": "changed"}},
            "bank_account_counts": {"Checking": 1},
            "bank_transaction_counts": {"Checking": {"Bank Account": 5}},
        }

        result = verify_plaid_item_migration(before, after)

        self.assertFalse(result["ok"])
        self.assertIn("Plaid Item state changed: Checking", result["errors"])

    def test_migration_verification_rejects_account_or_transaction_changes(self):
        before = {
            "item_count": 1,
            "items": {"Checking": {"profile": None, "state_fingerprint": "a"}},
            "bank_account_counts": {"Checking": 1},
            "bank_transaction_counts": {"Checking": {"Bank Account": 5}},
        }
        after = {
            "item_count": 1,
            "items": {"Checking": {"profile": "business", "state_fingerprint": "a"}},
            "bank_account_counts": {"Checking": 2},
            "bank_transaction_counts": {"Checking": {"Bank Account": 6}},
        }

        result = verify_plaid_item_migration(before, after)

        self.assertFalse(result["ok"])
        self.assertIn("Bank Account mappings changed", result["errors"])
        self.assertIn("Bank Transaction counts changed", result["errors"])
