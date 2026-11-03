"""Offline smoke tests for the production-staging runner's fail-closed guards."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "production_batch", ROOT / "scripts/commerce_production_staging_batch.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ProductionBatchTests(unittest.TestCase):
    def record(self, enabled=True):
        return {"content": {"source_payload": __import__("json").dumps(
                    {"product": {"enabled": enabled}})},
                "mapping": {"sync_enabled": 0},
                "woocommerce": {
                    "status": "draft", "catalog_visibility": "hidden",
                    "stock_quantity": 0, "manage_stock": True,
                    "backorders": "no",
                    "meta_data": [{"key": "_rootedops_ecwid_enabled",
                                   "value": "yes" if enabled else "no"}]}}

    def test_read_only_preflight_rejects_disabled_source(self):
        with self.assertRaisesRegex(ValueError, "Disabled-source"):
            self.compiled([self.record(False)])

    def test_requires_provenance(self):
        bad = self.record()
        bad["woocommerce"]["meta_data"] = []
        with self.assertRaisesRegex(ValueError, "provenance"):
            self.compiled([bad])

    def test_rejects_sellable_stock(self):
        bad = self.record()
        bad["woocommerce"]["stock_quantity"] = 1
        with self.assertRaisesRegex(ValueError, "non-sellable"):
            self.compiled([bad])

    def test_requires_small_batches(self):
        with self.assertRaisesRegex(ValueError, "one through five"):
            self.compiled([self.record() for _ in range(6)])

    def compiled(self, records):
        import tempfile
        import json
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "batch.json"
            path.write_text(json.dumps({"records": records}))
            return module.compiled_guard(path)


if __name__ == "__main__":
    unittest.main()
