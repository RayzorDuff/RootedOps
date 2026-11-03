"""Focused offline safety tests for live sales-tax inventory."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import commerce_tax_inventory as inventory

class TaxInventoryTests(unittest.TestCase):
    def test_live_inventory_is_read_only(self):
        code=inventory.ERP_READ
        self.assertIn('frappe.init(site="erp.danks.store")',code)
        self.assertIn('frappe.db.rollback()',code)
        self.assertNotIn('frappe.db.commit()',code)
        self.assertNotIn('frappe.get_doc("Sales Invoice"',code)
        self.assertNotIn('frappe.get_doc("Salary Slip"',code)
        self.assertIn('"writes":False',code)
        self.assertIn('"Tax Rule"',code)
        self.assertIn('"Item Tax Template"',code)
        self.assertIn('"Accounts Settings"',code)

    def test_missing_live_deployment_rejected(self):
        with patch.object(inventory.subprocess,'run') as run:
            with self.assertRaisesRegex(ValueError,'Installed RootedOps deployment'):
                inventory.inspect(Path('/nonexistent/rootedops-tax-audit'))
            run.assert_not_called()

if __name__=="__main__":
    unittest.main()
