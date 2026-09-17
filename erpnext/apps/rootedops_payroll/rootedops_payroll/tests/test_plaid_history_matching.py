from unittest import TestCase

from rootedops_payroll.services.plaid_history_matching import (
    assign_db_safe_transaction_ids,
    classify_transaction_overlap,
    deterministic_plan_hash,
    match_candidate_accounts,
    plaid_bank_transaction_fields,
    plaid_transaction_tags,
    validate_backfill_classifications,
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


class TestPlaidHistoryImportSafety(TestCase):
    def test_native_plaid_tags_are_preserved(self):
        self.assertEqual(
            plaid_transaction_tags(
                {
                    "category": ["Service", "Utilities"],
                    "category_id": "18068005",
                }
            ),
            ["Service", "Utilities", "Plaid Cat. 18068005"],
        )

    def test_import_validation_requires_new_rows_before_coverage(self):
        valid = validate_backfill_classifications(
            [
                {
                    "bank_account": "Checking",
                    "date": "2026-06-21",
                    "deposit": "0.00",
                    "withdrawal": "12.34",
                    "transaction_id": "historical-1",
                    "status": "new",
                },
                {
                    "bank_account": "Checking",
                    "date": "2026-06-22",
                    "deposit": "0.00",
                    "withdrawal": "10.00",
                    "transaction_id": "replacement-id",
                    "status": "strong_fallback_match",
                },
            ],
            {"Checking": "2026-06-22"},
        )
        self.assertEqual(valid["new_count"], 1)

        with self.assertRaisesRegex(ValueError, "not before existing coverage"):
            validate_backfill_classifications(
                [
                    {
                        "bank_account": "Checking",
                        "date": "2026-06-22",
                        "deposit": "0.00",
                        "withdrawal": "12.34",
                        "transaction_id": "unsafe-new",
                        "status": "new",
                    }
                ],
                {"Checking": "2026-06-22"},
            )

    def test_import_validation_rejects_weak_or_ambiguous_matches(self):
        with self.assertRaisesRegex(ValueError, "Unsafe transaction classifications"):
            validate_backfill_classifications(
                [
                    {
                        "bank_account": "Checking",
                        "date": "2026-06-22",
                        "deposit": "0.00",
                        "withdrawal": "12.34",
                        "transaction_id": "candidate",
                        "status": "ambiguous_amount_date_match",
                    }
                ],
                {"Checking": "2026-06-22"},
            )

    def test_plan_hash_is_deterministic_for_key_order(self):
        self.assertEqual(
            deterministic_plan_hash({"b": 2, "a": {"y": 2, "x": 1}}),
            deterministic_plan_hash({"a": {"x": 1, "y": 2}, "b": 2}),
        )


class TestPlaidHistoryDatabaseSafeIds(TestCase):
    def test_case_only_provider_ids_receive_distinct_deterministic_storage_ids(self):
        first = "kQ4PDzRRw8Cm4w7NKdKpSwBB98yv9KC0rk14k"
        second = "kQ4PDzRRw8Cm4w7NKdKpSwBB98yv9KC0rk14K"
        result = assign_db_safe_transaction_ids(
            [
                {"transaction_id": first, "bank_account": "Checking"},
                {"transaction_id": second, "bank_account": "Checking"},
            ]
        )

        self.assertEqual(result["transformed_count"], 2)
        self.assertEqual(len(result["collision_groups"]), 1)
        rows = {row["source_transaction_id"]: row for row in result["rows"]}
        self.assertTrue(rows[first]["storage_transaction_id"].startswith(first + "~cs-"))
        self.assertTrue(rows[second]["storage_transaction_id"].startswith(second + "~cs-"))
        self.assertNotEqual(
            rows[first]["storage_transaction_id"].casefold(),
            rows[second]["storage_transaction_id"].casefold(),
        )

        repeated = assign_db_safe_transaction_ids(
            [
                {"transaction_id": second, "bank_account": "Checking"},
                {"transaction_id": first, "bank_account": "Checking"},
            ]
        )
        repeated_rows = {row["source_transaction_id"]: row for row in repeated["rows"]}
        self.assertEqual(
            rows[first]["storage_transaction_id"],
            repeated_rows[first]["storage_transaction_id"],
        )
        self.assertEqual(
            rows[second]["storage_transaction_id"],
            repeated_rows[second]["storage_transaction_id"],
        )

    def test_noncolliding_provider_id_is_unchanged(self):
        result = assign_db_safe_transaction_ids(
            [{"transaction_id": "plaid-normal-1", "bank_account": "Checking"}]
        )
        self.assertEqual(result["transformed_count"], 0)
        self.assertEqual(
            result["rows"][0]["storage_transaction_id"],
            "plaid-normal-1",
        )

    def test_case_only_collision_with_existing_id_is_transformed(self):
        result = assign_db_safe_transaction_ids(
            [{"transaction_id": "PlaidABC", "bank_account": "Checking"}],
            existing_transaction_ids=["plaidabc"],
        )
        self.assertEqual(result["transformed_count"], 1)
        self.assertTrue(
            result["rows"][0]["storage_transaction_id"].startswith("PlaidABC~cs-")
        )

    def test_exact_existing_provider_id_remains_hard_error(self):
        with self.assertRaisesRegex(ValueError, "already exists in ERPNext"):
            assign_db_safe_transaction_ids(
                [{"transaction_id": "PlaidABC", "bank_account": "Checking"}],
                existing_transaction_ids=["PlaidABC"],
            )
