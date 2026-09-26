from unittest import TestCase
from unittest.mock import MagicMock, patch

from rootedops_payroll.services.plaid_link import (
    PlaidLinkError,
    bind_exchanged_item,
    create_link_token,
    exchange_public_token,
)


class TestPlaidLink(TestCase):
    @patch("rootedops_payroll.services.plaid_link.get_plaid_client")
    @patch("rootedops_payroll.services.plaid_link._require_profile", return_value="business")
    def test_create_link_token_uses_selected_profile(self, require_profile, get_client):
        client = MagicMock()
        client.post.return_value = {
            "link_token": "link-sandbox-token",
            "expiration": "2026-09-26T20:00:00Z",
            "request_id": "req-1",
        }
        get_client.return_value = client

        result = create_link_token("business", user_client_id="user-1")

        require_profile.assert_called_once_with("business")
        get_client.assert_called_once_with("business")
        self.assertEqual(result["profile"], "business")
        self.assertEqual(result["link_token"], "link-sandbox-token")
        client.post.assert_called_once()
        payload = client.post.call_args.args[1]
        self.assertEqual(payload["user"], {"client_user_id": "user-1"})
        self.assertEqual(payload["products"], ["transactions"])

    @patch("rootedops_payroll.services.plaid_link.get_plaid_client")
    @patch("rootedops_payroll.services.plaid_link._require_profile", return_value="personal")
    def test_exchange_uses_same_selected_profile(self, require_profile, get_client):
        client = MagicMock()
        client.post.return_value = {
            "access_token": "access-personal",
            "item_id": "item-personal",
        }
        get_client.return_value = client

        result = exchange_public_token("personal", "public-personal")

        require_profile.assert_called_once_with("personal")
        get_client.assert_called_once_with("personal")
        self.assertEqual(result["profile"], "personal")
        self.assertEqual(result["item_id"], "item-personal")
        self.assertEqual(result["access_token"], "access-personal")
        self.assertNotIn("access-personal", str(result["access_token_fingerprint"]))
        client.post.assert_called_once_with(
            "/item/public_token/exchange",
            {"public_token": "public-personal"},
        )

    @patch("rootedops_payroll.services.plaid_link.get_plaid_client")
    @patch("rootedops_payroll.services.plaid_link.exchange_public_token")
    @patch("rootedops_payroll.services.plaid_link._require_profile", return_value="business")
    @patch("rootedops_payroll.services.plaid_link._require_item_model")
    @patch("rootedops_payroll.services.plaid_link.frappe.db.commit")
    @patch("rootedops_payroll.services.plaid_link.frappe.get_doc")
    def test_bind_new_item_retains_selected_profile(
        self, get_doc, commit, require_item_model, require_profile, exchange, get_client
    ):
        bank = MagicMock()
        bank.get.side_effect = lambda field: None
        get_doc.return_value = bank
        exchange.return_value = {
            "profile": "business",
            "access_token": "access-business",
            "item_id": "item-business",
            "item_id_fingerprint": "item-fp",
        }
        client = MagicMock()
        client.post.side_effect = [
            {"item": {"item_id": "item-business"}},
            {"accounts": [{"account_id": "acct-1", "name": "Checking", "mask": "1234"}]},
        ]
        get_client.return_value = client

        result = bind_exchanged_item("New Bank", "business", "public-business")

        self.assertEqual(result["profile"], "business")
        self.assertEqual(result["account_count"], 1)
        bank.set.assert_any_call("plaid_profile", "business")
        bank.set.assert_any_call("plaid_access_token", "access-business")
        bank.save.assert_called_once_with(ignore_permissions=True)
        commit.assert_called_once()

    @patch("rootedops_payroll.services.plaid_link._require_profile", return_value="personal")
    @patch("rootedops_payroll.services.plaid_link._require_item_model")
    @patch("rootedops_payroll.services.plaid_link.frappe.get_doc")
    def test_bind_refuses_existing_access_token(self, get_doc, require_item_model, require_profile):
        bank = MagicMock()
        bank.get.side_effect = lambda field: "existing-token" if field == "plaid_access_token" else None
        get_doc.return_value = bank

        with self.assertRaises(PlaidLinkError):
            bind_exchanged_item("Existing Bank", "personal", "public-personal")
