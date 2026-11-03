"""Offline guards for MushroomProcess-owned ERP availability, no Stock Ledger writes."""
import ast
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "erpnext/apps/rootedops_commerce/rootedops_commerce"


class OperationalAvailabilityTests(unittest.TestCase):
    def test_api_compiles_and_refuses_unreviewed_writes(self):
        path = APP / "inventory_api.py"
        source = path.read_text()
        ast.parse(source, filename=str(path))
        self.assertIn("mp_inventory_erp_projection_enabled", source)
        self.assertIn('{"System Manager", "Sales Manager"}', source)
        self.assertIn("mushroomprocess_ecommerce_id", source)
        self.assertIn("Stale operational inventory snapshot refused", source)
        self.assertIn("Same-timestamp operational inventory snapshot conflict", source)
        for forbidden in ("Stock Entry", "Stock Ledger Entry", "Bin", "Payment Entry",
                          "Sales Invoice", "frappe.db.sql("):
            self.assertNotIn(forbidden, source)

    def test_read_model_is_not_an_erp_stock_doctype(self):
        path = APP / "rootedops_commerce/doctype/commerce_operational_availability/commerce_operational_availability.json"
        doc = json.loads(path.read_text())
        fields = {f["fieldname"]: f for f in doc["fields"]}
        self.assertIn("available_quantity", fields)
        self.assertIn("source_observed_at", fields)
        self.assertIn("source_hash", fields)
        self.assertEqual("Int", fields["available_quantity"]["fieldtype"])
        self.assertTrue(all(f.get("read_only") == 1 for f in doc["fields"]))
        self.assertFalse(any(p.get("write") for p in doc["permissions"]))

    def test_item_ui_displays_but_cannot_edit_mp_availability(self):
        api = (APP / "item_editorial.py").read_text()
        ui = (APP / "public/js/item_commerce.js").read_text()
        self.assertIn('"operational_availability"', api)
        self.assertIn("MushroomProcess available quantity (read-only)", ui)
        self.assertNotIn("available_quantity", (APP / "item_guard.py").read_text())

    def test_n8n_switches_off_by_default_in_compose(self):
        compose = (ROOT / "docker/docker-compose.yml").read_text()
        for name in ("MP_SYNC_ERP_ENABLED", "MP_SYNC_WOO_ENABLED"):
            self.assertIn(name + ": ${" + name + ":-false}", compose)
        self.assertIn("MP_SYNC_ECWID_ENABLED: ${MP_SYNC_ECWID_ENABLED:-true}", compose)
        self.assertIn("MP_SYNC_SNAPSHOT_ENABLED: ${MP_SYNC_SNAPSHOT_ENABLED:-false}", compose)


if __name__ == "__main__":
    unittest.main()
