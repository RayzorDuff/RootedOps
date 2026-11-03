"""Offline regression tests for canonical ERP content to native Item projection."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "erpnext/apps/rootedops_commerce/rootedops_commerce/catalog_sync.py"
spec = importlib.util.spec_from_file_location("rootedops_catalog_sync", MODULE)
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


def row(code="sku", desc="", source_desc="Source description", name="Product"):
    return {"item_code": code, "item_name": name,
            "description": desc, "public_title": name,
            "full_description": source_desc, "source_key": "ecwid:product:" + code}


class CatalogContentProjectionTests(unittest.TestCase):
    def test_empty_native_description_requires_projection(self):
        plan = sync.build_plan([row()])
        self.assertEqual(1, len(plan["changes"]))
        self.assertFalse(plan["conflicts"])
        self.assertEqual("Source description", plan["changes"][0]["to"])

    def test_replaying_identical_projection_is_noop(self):
        plan = sync.build_plan([row(desc="Source description")])
        self.assertEqual([], plan["changes"])
        self.assertEqual([], plan["conflicts"])

    def test_different_nonempty_description_refused(self):
        plan = sync.build_plan([row(desc="Edited directly in Item")])
        self.assertEqual([], plan["changes"])
        self.assertEqual("description", plan["conflicts"][0]["field"])

    def test_title_drift_refused(self):
        r = row()
        r["item_name"] = "Independent Item title"
        plan = sync.build_plan([r])
        self.assertEqual("item_name", plan["conflicts"][0]["field"])

    def test_empty_source_does_not_erase_native(self):
        plan = sync.build_plan([row(desc="", source_desc="")])
        self.assertFalse(plan["changes"])
        self.assertFalse(plan["conflicts"])

    def test_digest_tracks_content_drift_and_is_order_independent(self):
        a, b = row(code="a"), row(code="b")
        first = sync.build_plan([a, b])["digest"]
        self.assertEqual(first, sync.build_plan([b, a])["digest"])
        a["full_description"] = "Revised"
        self.assertNotEqual(first, sync.build_plan([a, b])["digest"])

    def test_apply_requires_explicit_digest_and_count_guard(self):
        import inspect
        source = inspect.getsource(sync.reconcile)
        self.assertIn('approve_digest != plan["digest"]', source)
        self.assertIn("len(rows) != expected_count", source)
        self.assertIn("frappe.db.rollback()", source)
        self.assertIn("frappe.db.commit()", source)
        self.assertNotIn("Sales Invoice\").insert", source)
        self.assertNotIn('frappe.db.set_value("Item"', source)


if __name__ == "__main__":
    unittest.main()
