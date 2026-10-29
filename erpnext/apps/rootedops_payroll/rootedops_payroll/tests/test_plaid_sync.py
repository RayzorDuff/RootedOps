from unittest import TestCase
from unittest.mock import MagicMock, patch

from rootedops_payroll.services.plaid_sync import PlaidSyncError, verify_plaid_item_sync


class TestPlaidSync(TestCase):
    @patch("rootedops_payroll.services.plaid_sync.get_plaid_client_for_bank")
    @patch("rootedops_payroll.services.plaid_sync.get_plaid_profile_for_bank", return_value="business")
    @patch("rootedops_payroll.services.plaid_sync._require_item_model")
    @patch("rootedops_payroll.services.plaid_sync.frappe.db.get_value", return_value="access-business")
    def test_sync_uses_item_profile_and_does_not_persist_cursor(
        self, get_value, require_model, get_profile, get_client
    ):
        client = MagicMock()
        client.post.side_effect = [
            {"item": {"item_id": "item-business", "institution_id": "ins-1", "institution_name": "Test Bank"}},
            {
                "added": [{"transaction_id": "tx-1"}],
                "modified": [],
                "removed": [],
                "has_more": False,
                "next_cursor": "cursor-business",
            },
        ]
        get_client.return_value = client

        result = verify_plaid_item_sync("Business Bank")

        get_profile.assert_called_once_with("Business Bank")
        get_client.assert_called_once_with("Business Bank")
        self.assertEqual(result["profile"], "business")
        self.assertEqual(result["added_count"], 1)
        self.assertFalse(result["safety"]["cursor_persisted"])
        self.assertEqual(result["safety"]["bank_transaction_writes"], 0)
        self.assertEqual(client.post.call_count, 2)
        self.assertEqual(
            client.post.call_args_list[1].args[0], "/transactions/sync"
        )
        self.assertEqual(
            client.post.call_args_list[1].args[1],
            {"access_token": "access-business", "count": 1},
        )

    @patch("rootedops_payroll.services.plaid_sync.get_plaid_client_for_bank")
    @patch("rootedops_payroll.services.plaid_sync.get_plaid_profile_for_bank", return_value="personal")
    @patch("rootedops_payroll.services.plaid_sync._require_item_model")
    @patch("rootedops_payroll.services.plaid_sync.frappe.db.get_value", return_value="access-personal")
    def test_second_profile_is_independent(self, get_value, require_model, get_profile, get_client):
        client = MagicMock()
        client.post.side_effect = [
            {"item": {"item_id": "item-personal", "institution_id": "ins-2"}},
            {"added": [], "modified": [], "removed": [], "has_more": False, "next_cursor": "cursor-personal"},
        ]
        get_client.return_value = client

        result = verify_plaid_item_sync("Personal Bank")

        self.assertEqual(result["profile"], "personal")
        self.assertEqual(result["item_id_fingerprint"], "0e377e5a78c2")
        get_client.assert_called_once_with("Personal Bank")

    @patch("rootedops_payroll.services.plaid_sync.get_plaid_client_for_bank")
    @patch("rootedops_payroll.services.plaid_sync.get_plaid_profile_for_bank", return_value="business")
    @patch("rootedops_payroll.services.plaid_sync._require_item_model")
    @patch("rootedops_payroll.services.plaid_sync.frappe.db.get_value", return_value="access-business")
    def test_cursor_is_forwarded_but_never_returned(
        self, get_value, require_model, get_profile, get_client
    ):
        client = MagicMock()
        client.post.side_effect = [
            {"item": {"item_id": "item-business"}},
            {"added": [], "modified": [], "removed": [], "has_more": True, "next_cursor": "cursor-2"},
        ]
        get_client.return_value = client

        result = verify_plaid_item_sync("Business Bank", cursor="cursor-1")

        payload = client.post.call_args_list[1].args[1]
        self.assertEqual(payload["cursor"], "cursor-1")
        self.assertNotIn("cursor-2", str(result))
        self.assertTrue(result["has_more"])

    @patch("rootedops_payroll.services.plaid_sync.frappe.db.get_value", return_value=None)
    @patch("rootedops_payroll.services.plaid_sync.get_plaid_profile_for_bank", return_value="business")
    @patch("rootedops_payroll.services.plaid_sync._require_item_model")
    def test_missing_access_token_is_rejected(self, require_model, get_profile, get_value):
        with self.assertRaises(PlaidSyncError):
            verify_plaid_item_sync("Business Bank")
