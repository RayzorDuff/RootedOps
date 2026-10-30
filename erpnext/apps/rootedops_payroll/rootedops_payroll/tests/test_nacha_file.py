import unittest
from decimal import Decimal

from rootedops_payroll.services.nacha_file import (
    ACHCredit,
    ACHDebit,
    NACHAProfile,
    generate_nacha,
    validate_nacha,
    validate_routing_number,
)


class TestNachaFile(unittest.TestCase):
    def profile(self, mode="unbalanced"):
        return NACHAProfile(
            "102000021",
            "1123456789",
            "HIGH PLAINS BANK",
            "DANK MUSHROOMS LLC",
            "DANK MUSHROOMS LLC",
            "1123456789",
            "10200002",
            "260930",
            balance_mode=mode,
        )

    def entry(self, savings=False, amount="1234.56", employee="TEST EMPLOYEE"):
        return ACHCredit(
            employee,
            employee,
            "021000021",
            "123456789",
            "Savings" if savings else "Checking",
            Decimal(amount),
            employee,
        )

    def debit(self, amount="1236.56", savings=False):
        return ACHDebit(
            "DANK MUSHROOMS LLC",
            "021000021",
            "987654321",
            "Savings" if savings else "Checking",
            Decimal(amount),
            "1123456789",
        )

    def test_payroll_description_in_required_batch_positions(self):
        lines = generate_nacha(
            self.profile(), [self.entry()],
            creation_date="260925", creation_time="1500",
        ).splitlines()
        self.assertEqual(lines[1][53:63], "PAYROLL   ")

    def test_validator_rejects_missing_payroll_description(self):
        lines = generate_nacha(
            self.profile(), [self.entry()],
            creation_date="260925", creation_time="1500",
        ).splitlines()
        lines[1] = lines[1][:53] + "SALARY    " + lines[1][63:]
        with self.assertRaisesRegex(ValueError, "PAYROLL"):
            validate_nacha("\n".join(lines))

    def test_accented_receiving_name_and_id_are_ascii(self):
        entry = ACHCredit(
            "HR-EMP-00001", "José Muñoz", "021000021", "123456789",
            "Checking", Decimal("84.78"), "José",
        )
        lines = generate_nacha(
            self.profile(), [entry],
            creation_date="260925", creation_time="1500",
        ).splitlines()
        self.assertEqual(lines[2][54:76].rstrip(), "JOSE MUNOZ")
        self.assertEqual(lines[2][39:54].rstrip(), "JOSE")
        self.assertTrue(all(len(line) == 94 and line.isascii() for line in lines))

    def test_nontransliterable_receiving_name_rejected(self):
        entry = ACHCredit(
            "HR-EMP-00001", "李明", "021000021", "123456789",
            "Checking", Decimal("84.78"),
        )
        with self.assertRaisesRegex(ValueError, "printable ASCII"):
            generate_nacha(
                self.profile(), [entry],
                creation_date="260925", creation_time="1500",
            )

    def test_validator_rejects_non_ascii_record(self):
        lines = generate_nacha(
            self.profile(), [self.entry()],
            creation_date="260925", creation_time="1500",
        ).splitlines()
        lines[2] = lines[2][:54] + "É" + lines[2][55:]
        with self.assertRaisesRegex(ValueError, "printable ASCII"):
            validate_nacha("\n".join(lines))

    def test_payroll_description_allows_three_character_suffix(self):
        lines = generate_nacha(
            self.profile(), [self.entry()],
            creation_date="260925", creation_time="1500",
        ).splitlines()
        lines[1] = lines[1][:53] + "PAYROLL 02" + lines[1][63:]
        self.assertEqual(validate_nacha("\n".join(lines))["entry_count"], 1)
        lines[1] = lines[1][:53] + "PAYROLLEMP" + lines[1][63:]
        self.assertEqual(validate_nacha("\n".join(lines))["entry_count"], 1)

    def test_common_unicode_name_transliteration(self):
        cases = {
            "O’Brien": "O'BRIEN",
            "Łukasz": "LUKASZ",
            "Søren": "SOREN",
            "Æsa": "AESA",
            "Jean–Luc": "JEAN-LUC",
            "Œdipe": "OEDIPE",
            "Đorđe": "DORDE",
            "Þóra": "THORA",
        }
        for original, expected in cases.items():
            with self.subTest(name=original):
                entry = ACHCredit(
                    "HR-EMP-00001", original, "021000021",
                    "123456789", "Checking", Decimal("84.78"),
                )
                lines = generate_nacha(
                    self.profile(), [entry],
                    creation_date="260925", creation_time="1500",
                ).splitlines()
                self.assertEqual(lines[2][54:76].rstrip(), expected)
                self.assertTrue(all(len(line) == 94 and line.isascii() for line in lines))

    def test_unsupported_name_error_identifies_employee_and_field(self):
        entry = ACHCredit(
            "HR-EMP-00077", "李明", "021000021", "123456789",
            "Checking", Decimal("84.78"),
        )
        with self.assertRaisesRegex(ValueError, "Employee HR-EMP-00077: Receiving Name"):
            generate_nacha(
                self.profile(), [entry],
                creation_date="260925", creation_time="1500",
            )

    def test_unsupported_individual_id_error_identifies_employee_and_field(self):
        entry = ACHCredit(
            "HR-EMP-00077", "TEST EMPLOYEE", "021000021", "123456789",
            "Checking", Decimal("84.78"), "李明",
        )
        with self.assertRaisesRegex(ValueError, "Employee HR-EMP-00077: Individual Identification"):
            generate_nacha(
                self.profile(), [entry],
                creation_date="260925", creation_time="1500",
            )

    def test_checking_and_savings(self):
        text = generate_nacha(
            self.profile(),
            [self.entry(), self.entry(True, "2.00", "SECOND EMP")],
            creation_date="260925",
            creation_time="1500",
        )
        self.assertEqual(validate_nacha(text)["entry_count"], 2)
        lines = text.splitlines()
        self.assertEqual(lines[2][1:3], "22")
        self.assertEqual(lines[3][1:3], "32")

        self.assertEqual(lines[2][29:39], "0000123456")
        self.assertEqual(lines[2][39:54].rstrip(), "TEST EMPLOYEE")
        self.assertEqual(lines[2][54:76].rstrip(), "TEST EMPLOYEE")
        self.assertEqual(lines[2][76:78], "00")
        self.assertEqual(lines[2][78], "0")

    def test_balanced_funding_entry(self):
        text = generate_nacha(
            self.profile("balanced"),
            [self.entry(False, "100.01"), self.entry(True, "23.45", "SECOND EMP")],
            debit_entry=self.debit("123.46"),
            creation_date="260925",
            creation_time="1500",
        )
        result = validate_nacha(text)
        self.assertEqual(result["entry_count"], 3)
        self.assertEqual(result["debit_total_cents"], 12346)
        self.assertEqual(result["credit_total_cents"], 12346)

        lines = text.splitlines()
        self.assertEqual(lines[1][1:4], "200")
        self.assertEqual(lines[2][1:3], "27")
        self.assertEqual(lines[3][1:3], "22")
        self.assertEqual(lines[4][1:3], "32")
        self.assertEqual(lines[1][69:75], "260930")
        self.assertEqual(lines[5][20:32], "000000012346")
        self.assertEqual(lines[5][32:44], "000000012346")
        self.assertEqual(lines[6][31:43], "000000012346")
        self.assertEqual(lines[6][43:55], "000000012346")

    def test_balanced_requires_offset(self):
        with self.assertRaises(ValueError):
            generate_nacha(
                self.profile("balanced"),
                [self.entry(False, "100.00")],
                creation_date="260925",
                creation_time="1500",
            )

    def test_balanced_offset_must_equal_credits(self):
        with self.assertRaises(ValueError):
            generate_nacha(
                self.profile("balanced"),
                [self.entry(False, "100.00")],
                debit_entry=self.debit("99.99"),
                creation_date="260925",
                creation_time="1500",
            )

    def test_effective_date_cannot_be_stale(self):
        with self.assertRaises(ValueError):
            generate_nacha(
                self.profile("unbalanced"),
                [self.entry(False, "100.00")],
                creation_date="261001",
                creation_time="0900",
            )

    def test_fixed_width_and_blocking(self):
        text = generate_nacha(
            self.profile(),
            [self.entry()],
            creation_date="260925",
            creation_time="1500",
        )
        self.assertEqual(len(text.splitlines()), 10)
        self.assertTrue(all(len(x) == 94 for x in text.splitlines()))

    def test_hash_and_totals(self):
        result = validate_nacha(
            generate_nacha(
                self.profile(),
                [self.entry(False, "100.01")],
                creation_date="260925",
                creation_time="1500",
            )
        )
        self.assertEqual(result["credit_total_cents"], 10001)
        self.assertEqual(result["debit_total_cents"], 0)

    def test_invalid_routing_rejected(self):
        with self.assertRaises(ValueError):
            validate_routing_number("123456789")

    def test_duplicate_trace_rejected(self):
        text = generate_nacha(
            self.profile(),
            [self.entry(), self.entry(False, "2.00", "SECOND EMP")],
            creation_date="260925",
            creation_time="1500",
        )
        lines = text.splitlines()
        lines[3] = lines[2]
        with self.assertRaises(ValueError):
            validate_nacha("\n".join(lines))


if __name__ == "__main__":
    unittest.main()
