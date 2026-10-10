from unittest import TestCase

from rootedops_payroll.services.signaturegate_deposits import (
    SignatureGateDepositError,
    _fingerprint_change_requires_review,
    _select_unique_match,
    _to_cents,
    list_signaturegate_cash_deposit_bank_accounts,
)


class TestSignatureGateDepositMatching(TestCase):
    def test_canvas_opening_deposit_split_is_unique(self):
        candidates = [
            {
                "name": "ACC-BTN-2026-00602",
                "date": "2026-10-08",
                "amount_cents": 73200,
            },
            {
                "name": "ACC-BTN-2026-00604",
                "date": "2026-10-08",
                "amount_cents": 500,
            },
            {
                "name": "ACC-BTN-2026-00603",
                "date": "2026-10-09",
                "amount_cents": 137358,
            },
        ]

        posting_date, rows = _select_unique_match(candidates, 73700)

        self.assertEqual(posting_date, "2026-10-08")
        self.assertEqual(
            {row["name"] for row in rows},
            {"ACC-BTN-2026-00602", "ACC-BTN-2026-00604"},
        )

    def test_ambiguous_bank_subsets_are_rejected(self):
        candidates = [
            {"name": "A", "date": "2026-10-08", "amount_cents": 5000},
            {"name": "B", "date": "2026-10-08", "amount_cents": 5000},
            {"name": "C", "date": "2026-10-08", "amount_cents": 10000},
        ]

        with self.assertRaises(SignatureGateDepositError):
            _select_unique_match(candidates, 10000)

    def test_money_conversion_is_cent_exact(self):
        self.assertEqual(_to_cents("732.00"), 73200)
        self.assertEqual(_to_cents("5"), 500)
        self.assertEqual(_to_cents("1373.58"), 137358)



class _Event:
    def __init__(self, status, request_fingerprint):
        self.status = status
        self.request_fingerprint = request_fingerprint


class TestSignatureGateDepositIdempotency(TestCase):
    def test_failed_event_may_retry_with_corrected_payload(self):
        event = _Event("Failed", "old-fingerprint")
        self.assertFalse(
            _fingerprint_change_requires_review(event, "new-fingerprint")
        )

    def test_succeeded_event_rejects_changed_payload(self):
        event = _Event("Succeeded", "old-fingerprint")
        self.assertTrue(
            _fingerprint_change_requires_review(event, "new-fingerprint")
        )



class TestSignatureGateBankAccountOptions(TestCase):
    def test_active_company_bank_accounts_are_returned_as_safe_options(self):
        from unittest.mock import patch

        rows = [
            {
                "name": "BASIC BUSINESS CHECKING - Canvas Credit Union",
                "bank": "Canvas Credit Union",
                "account_name": "BASIC BUSINESS CHECKING",
                "account": "BASIC BUSINESS CHECKING - Canvas Credit Union - RP",
                "mask": "2145",
                "is_default": 1,
            }
        ]

        with patch(
            "rootedops_payroll.services.signaturegate_deposits.frappe.get_all",
            return_value=rows,
        ) as get_all:
            result = list_signaturegate_cash_deposit_bank_accounts()

        self.assertTrue(result["ok"])
        self.assertEqual(result["company"], "Rooted Psyche")
        self.assertEqual(
            result["accounts"][0]["value"],
            "BASIC BUSINESS CHECKING - Canvas Credit Union",
        )
        self.assertIn("Canvas Credit Union", result["accounts"][0]["label"])
        self.assertNotIn("integration_id", result["accounts"][0])
        get_all.assert_called_once_with(
            "Bank Account",
            filters={
                "company": "Rooted Psyche",
                "disabled": 0,
                "is_company_account": 1,
            },
            fields=[
                "name",
                "bank",
                "account_name",
                "account",
                "mask",
                "is_default",
            ],
            order_by="is_default desc, bank asc, account_name asc, name asc",
            limit_page_length=0,
        )
