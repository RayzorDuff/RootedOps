from unittest import TestCase
from unittest.mock import MagicMock, patch

from rootedops_payroll.services.plaid_client import (
    PlaidClient,
    PlaidClientError,
    get_plaid_client,
    get_plaid_client_for_item,
)


class TestPlaidClient(TestCase):
    @patch("rootedops_payroll.services.plaid_client.resolve_plaid_profile")
    def test_profile_resolution_is_centralized(self, resolve):
        resolve.return_value = {
            "profile": "business",
            "environment": "production",
            "base_url": "https://production.plaid.com",
            "client_id": "client-business",
            "secret": "secret-business",
        }

        client = get_plaid_client("business")

        resolve.assert_called_once_with("business")
        self.assertEqual(client.profile, "business")
        self.assertEqual(client.environment, "production")
        self.assertEqual(client.base_url, "https://production.plaid.com")
        self.assertNotIn("secret-business", repr(client))
        self.assertNotIn("client-business", repr(client))

    @patch("rootedops_payroll.services.plaid_client.get_plaid_profile_for_bank")
    @patch("rootedops_payroll.services.plaid_client.get_plaid_client")
    def test_item_resolution_uses_its_assigned_profile(self, get_client, get_profile):
        get_profile.return_value = "personal"
        expected = MagicMock(profile="personal")
        get_client.return_value = expected

        result = get_plaid_client_for_item("SoFi")

        get_profile.assert_called_once_with("SoFi")
        get_client.assert_called_once_with("personal")
        self.assertIs(result, expected)

    @patch("rootedops_payroll.services.plaid_client.resolve_plaid_profile")
    def test_profile_failure_does_not_fallback(self, resolve):
        from rootedops_payroll.services.plaid_profile import PlaidProfileError

        resolve.side_effect = PlaidProfileError("Plaid profile personal is disabled.")

        with self.assertRaises(PlaidClientError) as ctx:
            get_plaid_client("personal")

        self.assertIn("personal", str(ctx.exception))
        self.assertNotIn("secret", str(ctx.exception).lower())

    @patch("rootedops_payroll.services.plaid_client.requests.post")
    def test_api_error_identifies_profile_without_credentials(self, post):
        response = MagicMock(status_code=400)
        response.json.return_value = {
            "error_type": "ITEM_ERROR",
            "error_code": "ITEM_LOGIN_REQUIRED",
            "error_message": "login required",
            "request_id": "req-123",
        }
        post.return_value = response
        client = PlaidClient(
            profile="personal",
            environment="production",
            base_url="https://production.plaid.com",
            client_id="client-secret-value",
            secret="super-secret-value",
        )

        with self.assertRaises(PlaidClientError) as ctx:
            client.post("/item/get", {"access_token": "token-value"})

        message = str(ctx.exception)
        self.assertIn("personal", message)
        self.assertIn("ITEM_LOGIN_REQUIRED", message)
        self.assertNotIn("client-secret-value", message)
        self.assertNotIn("super-secret-value", message)
        self.assertNotIn("token-value", message)

    @patch("rootedops_payroll.services.plaid_client.requests.post")
    def test_successful_request_uses_bound_profile_credentials(self, post):
        response = MagicMock(status_code=200)
        response.json.return_value = {"item": {"item_id": "item-1"}}
        post.return_value = response
        client = PlaidClient(
            profile="business",
            environment="production",
            base_url="https://production.plaid.com",
            client_id="client-business",
            secret="secret-business",
        )

        result = client.post("/item/get", {"access_token": "token-1"})

        self.assertEqual(result["item"]["item_id"], "item-1")
        post.assert_called_once_with(
            "https://production.plaid.com/item/get",
            json={
                "client_id": "client-business",
                "secret": "secret-business",
                "access_token": "token-1",
            },
            timeout=60,
        )
