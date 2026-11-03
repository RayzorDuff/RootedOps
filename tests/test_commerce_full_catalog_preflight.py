"""Focused offline checks for the 132-product catalog preflight."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "commerce_full_catalog_preflight",
    ROOT / "scripts/commerce_full_catalog_preflight.py",
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class FullCatalogPreflightTests(unittest.TestCase):
    def source(self):
        products = [
            {"id": i, "sku": f"SKU-{i}", "enabled": i % 2 == 0,
             "price": "1.00", "description": "source",
             "_combinations": [], "categoryIds": [160254004]}
            for i in sorted(module.APPROVED_PILOT_IDS)
        ]
        products.append({"id": 999, "sku": "00001", "enabled": False,
                         "price": "1", "description": "Historical POS",
                         "_combinations": [], "categoryIds": [199701664]})
        return {"store_id": "95802503", "products": products,
                "categories": [{"id": 160254004, "name": "Gourmet Mushrooms"}]}

    def test_cohorts_and_unknown_category_preserved(self):
        report = module.assess(self.source())
        self.assertEqual(report["total"], 23)
        self.assertEqual(len(report["cohorts"]["validated"]), 22)
        self.assertEqual(report["cohorts"]["disabled"], ["999"])
        self.assertEqual(report["unresolved_category_ids"], ["199701664"])
        self.assertFalse(report["destination_writes"])
        self.assertEqual(report["publication"], "draft")
        self.assertEqual(report["stock_quantity"], 0)

    def test_duplicate_sku_rejected(self):
        source = self.source()
        source["products"][-1]["sku"] = source["products"][0]["sku"].lower()
        with self.assertRaisesRegex(ValueError, "Missing or duplicate SKUs"):
            module.assess(source)

    def test_missing_combination_evidence_rejected(self):
        source = self.source()
        del source["products"][-1]["_combinations"]
        with self.assertRaisesRegex(ValueError, "combinations evidence"):
            module.assess(source)

    def test_variants_rejected(self):
        source = self.source()
        source["products"][-1]["_combinations"] = [{"id": 1001}]
        with self.assertRaisesRegex(ValueError, "Variable products"):
            module.assess(source)


if __name__ == "__main__":
    unittest.main()
