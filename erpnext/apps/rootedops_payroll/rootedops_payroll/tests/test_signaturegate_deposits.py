from unittest import TestCase

from rootedops_payroll.services.signaturegate_deposits import (
    SignatureGateDepositError,
    _select_unique_match,
    _to_cents,
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
