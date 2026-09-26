from unittest import TestCase
from unittest.mock import patch

from rootedops_payroll.services.plaid_history import (
    PlaidHistoricalBackfillError,
    _connection_profile_for_bank,
)


class TestPlaidHistoricalConnectionProfile(TestCase):
    @patch(
        "rootedops_payroll.services.plaid_history.get_plaid_profile_for_bank",
        return_value="personal",
    )
    def test_historical_bank_uses_assigned_connection_profile(self, get_profile):
        result = _connection_profile_for_bank("Personal Bank")

        self.assertEqual(result, "personal")
        get_profile.assert_called_once_with("Personal Bank")

    @patch(
        "rootedops_payroll.services.plaid_history.get_plaid_profile_for_bank",
        return_value="personal",
    )
    def test_historical_session_refuses_connection_profile_drift(self, get_profile):
        with self.assertRaisesRegex(
            PlaidHistoricalBackfillError,
            "changed during historical session",
        ):
            _connection_profile_for_bank("Personal Bank", expected_profile="business")

        get_profile.assert_called_once_with("Personal Bank")

    @patch(
        "rootedops_payroll.services.plaid_history.get_plaid_profile_for_bank",
        side_effect=RuntimeError("Plaid Item has no assigned connection profile"),
    )
    def test_missing_connection_profile_is_rejected(self, get_profile):
        with self.assertRaisesRegex(
            PlaidHistoricalBackfillError,
            "Cannot resolve Plaid Connection Profile",
        ):
            _connection_profile_for_bank("Unbound Bank")

        get_profile.assert_called_once_with("Unbound Bank")
