from unittest import TestCase
from unittest.mock import MagicMock, call, patch

from rootedops_payroll.services.plaid_erpnext_compat import (
    bind_stock_linked_bank_profile,
    enqueue_stock_compatible_synchronization,
    get_stock_plaid_profile,
    stock_sync_plan,
)


class TestStockPlaidProfileBinding(TestCase):
    @patch("rootedops_payroll.services.plaid_erpnext_compat._legacy_profile_rows")
    def test_unique_legacy_profile_is_selected(self, rows):
        rows.return_value = [{"name": "legacy-current", "is_default": 1}]
        self.assertEqual(get_stock_plaid_profile(), "legacy-current")

    @patch("rootedops_payroll.services.plaid_erpnext_compat._legacy_profile_rows")
    def test_stock_link_populates_blank_profile(self, rows):
        rows.return_value = [{"name": "legacy-current", "is_default": 1}]
        doc = MagicMock()
        doc.meta.has_field.return_value = True
        values = {
            "plaid_profile": None,
            "plaid_access_token": "access-token",
        }
        doc.get.side_effect = values.get

        bind_stock_linked_bank_profile(doc)

        doc.set.assert_called_once_with("plaid_profile", "legacy-current")

    @patch("rootedops_payroll.services.plaid_erpnext_compat._legacy_profile_rows")
    def test_stock_link_never_overwrites_existing_profile(self, rows):
        rows.return_value = [{"name": "legacy-current", "is_default": 1}]
        doc = MagicMock()
        doc.meta.has_field.return_value = True
        values = {
            "plaid_profile": "business",
            "plaid_access_token": "access-token",
        }
        doc.get.side_effect = values.get

        bind_stock_linked_bank_profile(doc)

        doc.set.assert_not_called()


class TestStockPlaidSyncPlan(TestCase):
    @patch("rootedops_payroll.services.plaid_erpnext_compat.get_plaid_client_for_bank")
    @patch("rootedops_payroll.services.plaid_erpnext_compat.frappe.get_doc")
    @patch("rootedops_payroll.services.plaid_erpnext_compat.frappe.db.get_value")
    @patch("rootedops_payroll.services.plaid_erpnext_compat.frappe.get_all")
    @patch("rootedops_payroll.services.plaid_erpnext_compat._legacy_profile_rows")
    def test_plan_skips_tokenless_unprofiled_and_nonlegacy_items(
        self, legacy_rows, get_all, get_value, get_doc, get_client
    ):
        legacy_rows.return_value = [{"name": "legacy-current", "is_default": 1}]
        get_all.return_value = [
            {"name": "Canvas Checking", "bank": "Canvas", "integration_id": "acct-canvas"},
            {"name": "Stale Checking", "bank": "Stale", "integration_id": "acct-stale"},
            {"name": "Unprofiled Checking", "bank": "Unprofiled", "integration_id": "acct-unprofiled"},
            {"name": "Personal Checking", "bank": "Personal", "integration_id": "acct-personal"},
        ]

        values = {
            ("Bank", "Canvas", "plaid_access_token"): "token-canvas",
            ("Bank", "Canvas", "plaid_profile"): "legacy-current",
            ("Bank", "Stale", "plaid_access_token"): None,
            ("Bank", "Stale", "plaid_profile"): None,
            ("Bank", "Unprofiled", "plaid_access_token"): "token-unprofiled",
            ("Bank", "Unprofiled", "plaid_profile"): None,
            ("Bank", "Personal", "plaid_access_token"): "token-personal",
            ("Bank", "Personal", "plaid_profile"): "personal",
        }
        get_value.side_effect = lambda doctype, name, field: values[(doctype, name, field)]

        get_doc.return_value.get_password.return_value = "token-canvas"
        get_client.return_value.post.return_value = {"accounts": [{"account_id": "acct-canvas"}]}
        plan = stock_sync_plan()

        self.assertEqual(
            plan["candidates"],
            [
                {
                    "bank_account": "Canvas Checking",
                    "bank": "Canvas",
                    "profile": "legacy-current",
                }
            ],
        )
        self.assertEqual(len(plan["skipped"]), 3)
        get_all.assert_called_once_with(
            "Bank Account",
            filters={
                "integration_id": ["is", "set"],
                "disabled": 0,
            },
            fields=["name", "bank", "integration_id"],
            order_by="name asc",
            limit_page_length=0,
        )

    @patch("rootedops_payroll.services.plaid_erpnext_compat.get_plaid_client_for_bank")
    @patch("rootedops_payroll.services.plaid_erpnext_compat.frappe.get_doc")
    @patch("rootedops_payroll.services.plaid_erpnext_compat.frappe.db.get_value")
    @patch("rootedops_payroll.services.plaid_erpnext_compat.frappe.get_all")
    @patch("rootedops_payroll.services.plaid_erpnext_compat._legacy_profile_rows")
    def test_membership_mismatch_and_lookup_failure_fail_closed(
        self, legacy_rows, get_all, get_value, get_doc, get_client
    ):
        legacy_rows.return_value = [{"name": "legacy-current", "is_default": 1}]
        get_all.return_value = [
            {"name": "Stale", "bank": "One", "integration_id": "old-id"},
            {"name": "Current", "bank": "One", "integration_id": "new-id"},
            {"name": "Failed", "bank": "Two", "integration_id": "other-id"},
        ]
        get_value.side_effect = lambda doctype, name, field: (
            "legacy-current" if field == "plaid_profile" else "present-token"
        )
        get_doc.return_value.get_password.return_value = "present-token"
        def pick_client(bank):
            client = MagicMock()
            if bank == "One":
                client.post.return_value = {"accounts": [{"account_id": "new-id"}]}
            else:
                client.post.side_effect = RuntimeError("API unavailable")
            return client
        get_client.side_effect = pick_client
        result = stock_sync_plan()
        self.assertEqual([r["bank_account"] for r in result["candidates"]], ["Current"])
        self.assertEqual({r["bank_account"] for r in result["skipped"]}, {"Stale", "Failed"})
        self.assertEqual(get_client.call_count, 2)

    @patch("rootedops_payroll.services.plaid_erpnext_compat.get_plaid_client_for_bank")
    @patch("rootedops_payroll.services.plaid_erpnext_compat.frappe.get_doc")
    @patch("rootedops_payroll.services.plaid_erpnext_compat.frappe.db.get_value")
    @patch("rootedops_payroll.services.plaid_erpnext_compat.frappe.get_all")
    @patch("rootedops_payroll.services.plaid_erpnext_compat._legacy_profile_rows")
    def test_two_active_mappings_to_same_plaid_account_both_fail_closed(
        self, legacy_rows, get_all, get_value, get_doc, get_client
    ):
        legacy_rows.return_value = [{"name": "legacy-current", "is_default": 1}]
        get_all.return_value = [
            {"name": "Checking A", "bank": "Bank", "integration_id": "shared-id"},
            {"name": "Checking B", "bank": "Bank", "integration_id": "shared-id"},
            {"name": "Savings", "bank": "Bank", "integration_id": "unique-id"},
        ]
        get_value.side_effect = lambda doctype, name, field: (
            "legacy-current" if field == "plaid_profile" else "present-token"
        )
        get_doc.return_value.get_password.return_value = "present-token"
        get_client.return_value.post.return_value = {"accounts": [
            {"account_id": "shared-id"}, {"account_id": "unique-id"}
        ]}

        plan = stock_sync_plan()
        self.assertEqual([row["bank_account"] for row in plan["candidates"]], ["Savings"])
        self.assertEqual(
            {row["bank_account"] for row in plan["skipped"]},
            {"Checking A", "Checking B"},
        )
        self.assertTrue(all("Duplicate active" in row["reason"] for row in plan["skipped"]))
        get_client.assert_called_once_with("Bank")

    @patch("rootedops_payroll.services.plaid_erpnext_compat.frappe.enqueue")
    @patch("rootedops_payroll.services.plaid_erpnext_compat.stock_sync_plan")
    def test_enqueue_queues_only_safe_candidates(self, plan, enqueue):
        plan.return_value = {
            "candidates": [
                {
                    "bank_account": "Canvas Checking",
                    "bank": "Canvas",
                    "profile": "legacy-current",
                },
                {
                    "bank_account": "SoFi Checking",
                    "bank": "SoFi",
                    "profile": "legacy-current",
                },
            ],
            "skipped": [
                {
                    "bank_account": "Old Checking",
                    "bank": "Old Bank",
                    "reason": "Bank has no Plaid access token",
                }
            ],
        }

        result = enqueue_stock_compatible_synchronization()

        self.assertEqual(result["queued_count"], 2)
        self.assertEqual(result["skipped_count"], 1)
        self.assertEqual(
            enqueue.call_args_list,
            [
                call(
                    (
                        "erpnext.erpnext_integrations.doctype.plaid_settings."
                        "plaid_settings.sync_transactions"
                    ),
                    bank="Canvas",
                    bank_account="Canvas Checking",
                ),
                call(
                    (
                        "erpnext.erpnext_integrations.doctype.plaid_settings."
                        "plaid_settings.sync_transactions"
                    ),
                    bank="SoFi",
                    bank_account="SoFi Checking",
                ),
            ],
        )
