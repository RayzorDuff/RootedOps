import unittest
from datetime import date, datetime
from decimal import Decimal

from rootedops_payroll.services.nacha_export_core import build_payroll_ach_export
from rootedops_payroll.services.nacha_file import ACHCredit, NACHAProfile


class TestNACHAExportCore(unittest.TestCase):
    def setUp(self):
        self.profile = NACHAProfile(
            immediate_destination="102000021",
            immediate_origin="1123456789",
            destination_name="TEST BANK",
            origin_name="DANK MUSHROOMS LLC",
            company_name="DANK MUSHROOMS",
            company_id="1123456789",
            odfi_identification="10200002",
            effective_entry_date="260925",
            balance_mode="unbalanced",
        )

    def test_single_corban_export_is_cent_exact_and_validated(self):
        result = build_payroll_ach_export(
            profile=self.profile,
            entries=[ACHCredit(
                employee="HR-EMP-00008",
                account_name="CORBEN RICHARD BURKHART",
                routing_number="021000021",
                account_number="123456789",
                account_type="Checking",
                amount=Decimal("84.78"),
                individual_id="HR-EMP-00008",
            )],
            payroll_entry="HR-PRUN-2026-00054",
            effective_date=date(2026, 9, 25),
            export_version=1,
            creation_datetime=datetime(2026, 9, 25, 15, 0),
        )
        self.assertEqual(result.entry_count, 1)
        self.assertEqual(result.credit_total_cents, 8478)
        self.assertEqual(result.record_count, 10)
        self.assertEqual(len(result.content.splitlines()), 10)
        self.assertEqual(len(result.sha256), 64)
        self.assertEqual(result.filename, "rootedops_payroll_HR-PRUN-2026-00054_20260925_v1.ach")

    def test_export_version_changes_filename(self):
        result = build_payroll_ach_export(
            profile=self.profile,
            entries=[ACHCredit(
                employee="E1", account_name="TEST", routing_number="021000021",
                account_number="123", account_type="Checking", amount="1.00",
            )],
            payroll_entry="PE-1",
            effective_date=date(2026, 9, 25),
            export_version=2,
            creation_datetime=datetime(2026, 9, 25, 15, 0),
        )
        self.assertTrue(result.filename.endswith("_v2.ach"))


if __name__ == "__main__":
    unittest.main()
