"""Offline contracts for first product batch independent reconciliation."""
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import commerce_verify_production_pilot as verified


class ReconciliationTests(unittest.TestCase):
    def test_read_only_contract(self):
        self.assertIn("frappe.db.rollback()",verified.ERP_READ)
        self.assertNotIn("frappe.db.commit()",verified.ERP_READ)
        self.assertNotIn("import_product(",verified.ERP_READ)
        self.assertIn("rootedops_commerce.api import catalog",verified.ERP_READ)
        self.assertIn("woocommerce_coming_soon",verified.WOO_READ)
        self.assertIn("wc_get_product_id_by_sku",verified.WOO_READ)
        self.assertNotIn("wp_insert_post",verified.WOO_READ)
        self.assertNotIn("new WC_Product",verified.WOO_READ)
        self.assertIn("get_stock_status()!=='outofstock'",verified.WOO_READ)

    def test_missing_receipt_refuses_before_destination(self):
        with patch.object(verified,"verify_compiled",return_value=[{}]*5),\
             patch.object(verified,"guard_live") as guard:
            with self.assertRaisesRegex(ValueError,"Import receipt required"):
                verified.reconcile(Path("/tmp"),Path("/tmp/unimportant"),verified.BATCHES[1][0],
                    Path("/tmp/pilot-01-import-receipt.json"))
            guard.assert_not_called()


if __name__=="__main__":
    unittest.main()
