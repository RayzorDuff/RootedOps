"""Readiness runner never performs product writes."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import commerce_production_batch_readiness as ready


class ProductionReadinessContracts(unittest.TestCase):
    def test_readonly_native_payloads_and_exact_targets(self):
        self.assertIn("frappe.init(site='erp.danks.store')", ready.ERP)
        self.assertIn("frappe.db.rollback()", ready.ERP)
        self.assertNotIn("frappe.db.commit()", ready.ERP)
        self.assertIn("Standard Selling", ready.ERP)
        self.assertIn("woocommerce_coming_soon", ready.WP)
        self.assertIn("wp_attachment_is_image", ready.WP)
        self.assertIn("wc_get_product_id_by_sku", ready.WP)
        self.assertNotIn("wp_insert_post", ready.WP)
        self.assertNotIn("wp_insert_attachment", ready.WP)

    def test_request_failure_never_returns_apparent_success(self):
        with patch.object(ready.subprocess,"run") as run:
            run.return_value.returncode=1
            run.return_value.stderr="Denied"
            with self.assertRaisesRegex(RuntimeError,"Denied"):
                ready.run_native(["command"],{"records":[]})


if __name__=="__main__":
    unittest.main()
