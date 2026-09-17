from unittest import TestCase

from rootedops_payroll.services.plaid_history_matching import (
    classify_transaction_overlap,
    match_candidate_accounts,
    plaid_bank_transaction_fields,
)


class TestPlaidHistoryMatching(TestCase):
    def test_plaid_amount_polarity_matches_erpnext_v16(self):
        withdrawal = plaid_bank_transaction_fields(
            {
                "amount": 25.12,
                "date": "2026-06-01",
                "name": "Utility",
                "payment_meta": {},
            }
        )
        deposit = plaid_bank_transaction_fields(
            {
                "amount": -125.55,
                "date": "2026-06-02",
                "name": "Deposit",
                "payment_meta": {},
            }
        )

        self.assertEqual(str(withdrawal["withdrawal"]), "25.12")
        self.assertEqual(str(withdrawal["deposit"]), "0.00")
        self.assertEqual(str(deposit["deposit"]), "125.55")
        self.assertEqual(str(deposit["withdrawal"]), "0.00")

    def test_account_mapping_prefers_mask_type_subtype_and_name(self):
        mappings = match_candidate_accounts(
            [
                {
                    "bank_account": "Canonical Checking",
                    "account_id": "old-checking",
                    "mask": "1234",
                    "type": "depository",
                    "subtype": "checking",
                    "name": "Business Checking",
                },
                {
                    "bank_account": "Canonical Savings",
                    "account_id": "old-savings",
                    "mask": "9999",
                    "type": "depository",
                    "subtype": "savings",
                    "name": "Tax Savings",
                },
            ],
            [
                {
                    "account_id": "new-savings",
                    "mask": "9999",
                    "type": "depository",
                    "subtype": "savings",
                    "name": "Tax Savings",
                },
                {
                    "account_id": "new-checking",
                    "mask": "1234",
                    "type": "depository",
                    "subtype": "checking",
                    "name": "Business Checking",
                },
            ],
        )

        self.assertEqual(mappings[0]["candidate_account_id"], "new-checking")
        self.assertEqual(mappings[1]["candidate_account_id"], "new-savings")
        self.assertTrue(all(row["status"] == "mapped" for row in mappings))

    def test_exact_transaction_id_must_stay_on_same_bank_account(self):
        result = classify_transaction_overlap(
            [
                {
                    "bank_account": "Checking",
                    "date": "2026-06-01",
                    "deposit": 0,
                    "withdrawal": 10,
                    "transaction_id": "plaid-1",
                    "description": "Store",
                    "reference_number": "Store",
                    "transaction_type": "place",
                }
            ],
            [
                {
                    "name": "BT-1",
                    "bank_account": "Savings",
                    "date": "2026-06-01",
                    "deposit": 0,
                    "withdrawal": 10,
                    "transaction_id": "plaid-1",
                    "description": "Store",
                    "reference_number": "Store",
                    "transaction_type": "place",
                }
            ],
        )

        self.assertEqual(result[0]["status"], "transaction_id_account_conflict")

    def test_strong_duplicate_matching_preserves_group_multiplicity(self):
        candidate = []
        existing = []
        for index in range(2):
            candidate.append(
                {
                    "bank_account": "Checking",
                    "date": "2026-06-01",
                    "deposit": 0,
                    "withdrawal": 15,
                    "transaction_id": f"new-{index}",
                    "description": "Coffee Shop",
                    "reference_number": "Coffee Shop",
                    "transaction_type": "place",
                }
            )
            existing.append(
                {
                    "name": f"BT-{index}",
                    "bank_account": "Checking",
                    "date": "2026-06-01",
                    "deposit": 0,
                    "withdrawal": 15,
                    "transaction_id": f"old-{index}",
                    "description": "Coffee Shop",
                    "reference_number": "Coffee Shop",
                    "transaction_type": "place",
                }
            )

        result = classify_transaction_overlap(candidate, existing)
        self.assertTrue(all(row["status"] == "strong_fallback_match" for row in result))
        self.assertTrue(all(row["group_multiplicity"] == 2 for row in result))

    def test_amount_and_date_only_match_is_never_silently_deduplicated(self):
        result = classify_transaction_overlap(
            [
                {
                    "bank_account": "Checking",
                    "date": "2026-06-01",
                    "deposit": 0,
                    "withdrawal": 20,
                    "transaction_id": "new-id",
                    "description": "Different description",
                    "reference_number": "Different description",
                    "transaction_type": "place",
                }
            ],
            [
                {
                    "name": "BT-1",
                    "bank_account": "Checking",
                    "date": "2026-06-01",
                    "deposit": 0,
                    "withdrawal": 20,
                    "transaction_id": "old-id",
                    "description": "Other merchant",
                    "reference_number": "Other merchant",
                    "transaction_type": "place",
                }
            ],
        )

        self.assertEqual(result[0]["status"], "ambiguous_amount_date_match")

    def test_unmatched_transaction_is_new(self):
        result = classify_transaction_overlap(
            [
                {
                    "bank_account": "Checking",
                    "date": "2026-05-01",
                    "deposit": 100,
                    "withdrawal": 0,
                    "transaction_id": "candidate",
                    "description": "Historical deposit",
                    "reference_number": "Historical deposit",
                    "transaction_type": "special",
                }
            ],
            [],
        )

        self.assertEqual(result[0]["status"], "new")
