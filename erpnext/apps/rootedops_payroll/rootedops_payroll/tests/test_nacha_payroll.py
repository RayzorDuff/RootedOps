import unittest
from datetime import datetime

from rootedops_payroll.services.nacha_payroll import (
    NachaPayrollValidationError,
    build_nacha_payroll_plan,
)


class TestNachaPayrollPlan(unittest.TestCase):
    def profile(self):
        return {
            "profile": "DML Payroll",
            "enabled": True,
            "certification_status": "Ready for Bank Test",
            "company": "Dank Mushrooms, LLC",
            "company_name": "Dank Mushrooms, LLC",
            "batch_company_name": "DANK MUSHROOMS",
            "company_id": "1123456789",
            "immediate_destination": "102000021",
            "immediate_origin": "1123456789",
            "immediate_destination_name": "HIGH PLAINS BANK",
            "immediate_origin_name": "DANK MUSHROOMS LLC",
            "originating_dfi_identification": "10200002",
            "reference_code": "",
            "balance_mode": "Unbalanced",
        }

    def test_mixed_ach_and_non_ach_plan(self):
        salary_slips = [
            {"name": "SAL-001", "employee": "EMP-001", "employee_name": "Employee A", "net_pay": 350.00, "docstatus": 1},
            {"name": "SAL-002", "employee": "EMP-002", "employee_name": "Employee B", "net_pay": 425.00, "docstatus": 1},
        ]
        configurations = {
            "EMP-001": {"active": 1, "payment_method": "ACH", "effective_date": "2026-01-01"},
            "EMP-002": {"active": 1, "payment_method": "Paper Check", "effective_date": "2026-01-01"},
        }
        credentials = {
            "EMP-001": {
                "routing_number": "021000021",
                "account_number": "123456789",
                "account_type": "Checking",
                "bank_name": "High Plains Bank",
                "account_holder_name": "Employee A",
                "routing_number_masked": "••••0021",
                "account_number_masked": "••••6789",
            }
        }

        result = build_nacha_payroll_plan(
            payroll_entry="HR-PRUN-001",
            company="Dank Mushrooms, LLC",
            pay_period_start="2026-09-18",
            pay_period_end="2026-09-24",
            effective_entry_date="2026-09-25",
            profile=self.profile(),
            salary_slips=salary_slips,
            payment_configurations=configurations,
            ach_credentials=credentials,
            creation_datetime=datetime(2026, 9, 25, 15, 0),
        )

        self.assertEqual(result["employee_count"], 2)
        self.assertEqual(result["ach_employee_count"], 1)
        self.assertEqual(result["ach_total"], 350.00)
        self.assertEqual(result["total_payroll_net_pay"], 775.00)
        self.assertEqual(result["excluded_count"], 1)
        self.assertEqual(result["formatter_validation"]["entry_count"], 1)
        self.assertTrue(result["read_only"])
        self.assertFalse(result["file_generated"])
        self.assertNotIn("123456789", str(result))
        self.assertNotIn("021000021", str(result))

    def test_duplicate_employee_salary_slips_are_rejected(self):
        with self.assertRaises(NachaPayrollValidationError):
            build_nacha_payroll_plan(
                payroll_entry="HR-PRUN-001",
                company="Dank Mushrooms, LLC",
                pay_period_start="2026-09-18",
                pay_period_end="2026-09-24",
                effective_entry_date="2026-09-25",
                profile=self.profile(),
                salary_slips=[
                    {"name": "SAL-001", "employee": "EMP-001", "employee_name": "Employee A", "net_pay": 350.00, "docstatus": 1},
                    {"name": "SAL-002", "employee": "EMP-001", "employee_name": "Employee A", "net_pay": 425.00, "docstatus": 1},
                ],
                payment_configurations={
                    "EMP-001": {"active": 1, "payment_method": "ACH", "effective_date": "2026-01-01"}
                },
                ach_credentials={
                    "EMP-001": {
                        "routing_number": "021000021",
                        "account_number": "123456789",
                        "account_type": "Checking",
                        "bank_name": "High Plains Bank",
                        "account_holder_name": "Employee A",
                    }
                },
                creation_datetime=datetime(2026, 9, 25, 15, 0),
            )

    def test_balanced_profile_is_rejected_until_offset_support_exists(self):
        profile = self.profile()
        profile["balance_mode"] = "Balanced"
        with self.assertRaises(NachaPayrollValidationError):
            build_nacha_payroll_plan(
                payroll_entry="HR-PRUN-001",
                company="Dank Mushrooms, LLC",
                pay_period_start="2026-09-18",
                pay_period_end="2026-09-24",
                effective_entry_date="2026-09-25",
                profile=profile,
                salary_slips=[
                    {"name": "SAL-001", "employee": "EMP-001", "employee_name": "Employee A", "net_pay": 350.00, "docstatus": 1}
                ],
                payment_configurations={
                    "EMP-001": {"active": 1, "payment_method": "ACH", "effective_date": "2026-01-01"}
                },
                ach_credentials={
                    "EMP-001": {
                        "routing_number": "021000021",
                        "account_number": "123456789",
                        "account_type": "Checking",
                        "bank_name": "High Plains Bank",
                        "account_holder_name": "Employee A",
                    }
                },
            )
