import unittest
from decimal import Decimal
from rootedops_payroll.services.nacha_file import *

class TestNachaFile(unittest.TestCase):
    def profile(self, mode="unbalanced"):
        return NACHAProfile("102000021", "1123456789", "HIGH PLAINS BANK", "DANK MUSHROOMS LLC", "DANK MUSHROOMS LLC", "1123456789", "10200002", "260930", balance_mode=mode)
    def entry(self, savings=False, amount="1234.56", employee="TEST EMPLOYEE"):
        return ACHCredit(employee, employee, "021000021", "123456789", "Savings" if savings else "Checking", Decimal(amount), employee)
    def test_checking_and_savings(self):
        text = generate_nacha(self.profile(), [self.entry(), self.entry(True, "2.00", "SECOND EMP")], creation_date="260925", creation_time="1500")
        self.assertEqual(validate_nacha(text)["entry_count"], 2)
        lines = text.splitlines()
        self.assertEqual(lines[2][1:3], "22")
        self.assertEqual(lines[3][1:3], "32")

        # PPD Entry Detail field positions:
        # 30-39 amount, 40-54 individual ID,
        # 55-76 receiving individual name,
        # 77-78 discretionary data, 79 addenda indicator,
        # 80-94 trace number.
        self.assertEqual(lines[2][29:39], "0000123456")
        self.assertEqual(lines[2][39:54].rstrip(), "TEST EMPLOYEE")
        self.assertEqual(lines[2][54:76].rstrip(), "TEST EMPLOYEE")
        self.assertEqual(lines[2][76:78], "00")
        self.assertEqual(lines[2][78], "0")
    def test_fixed_width_and_blocking(self):
        text = generate_nacha(self.profile(), [self.entry()], creation_date="260925", creation_time="1500")
        self.assertEqual(len(text.splitlines()), 10)
        self.assertTrue(all(len(x) == 94 for x in text.splitlines()))
    def test_hash_and_totals(self):
        result = validate_nacha(generate_nacha(self.profile(), [self.entry(False, "100.01")], creation_date="260925", creation_time="1500"))
        self.assertEqual(result["credit_total_cents"], 10001)
    def test_invalid_routing_rejected(self):
        with self.assertRaises(ValueError): validate_routing_number("123456789")
    def test_duplicate_trace_rejected(self):
        text = generate_nacha(self.profile(), [self.entry(), self.entry(False, "2.00", "SECOND EMP")], creation_date="260925", creation_time="1500")
        lines=text.splitlines(); lines[3]=lines[2]
        with self.assertRaises(ValueError): validate_nacha("\n".join(lines))

if __name__ == "__main__": unittest.main()
