"""Read-only media preparation from immutable Ecwid API source records."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from commerce_full_catalog_preflight import APPROVED_PILOT_IDS
from commerce_staging_media_inventory import prepare,write_private


class MediaPrepTests(unittest.TestCase):
    def fixture(self):
        ids=sorted(APPROVED_PILOT_IDS)
        products=[{"id":i,"sku":f"SKU-{i}","enabled":True,
                   "price":"9.95","description":"source",
                   "_combinations":[],"categoryIds":[160254004]}
                  for i in ids]
        products[0]["originalImageUrl"]="https://media.example.test/photo.jpg"
        products[0]["galleryImages"]=[
            {"url":"https://media.example.test/photo.jpg"},
            {"url":"https://media.example.test/photo2.jpg"}]
        products.append({"id":999,"sku":"00001","enabled":False,
                         "price":"1.00","description":"POS",
                         "_combinations":[],"categoryIds":[199701664]})
        return {"store_id":"95802503","products":products,
                "categories":[{"id":160254004,"name":"Gourmet Mushrooms"}]}

    def test_inventory_and_selection_preserve_provenance(self):
        selected,report=prepare(self.fixture())
        self.assertEqual(len(selected["products"]),22)
        self.assertEqual(report["catalog_totals"]["disabled"],1)
        self.assertEqual(report["unique_selected_media_urls"],2)
        self.assertEqual(report["pilot_products_missing_images"],21)
        self.assertEqual(report["media_hosts"],["media.example.test"])
        self.assertEqual(report["unresolved_categories"],["199701664"])
        self.assertFalse(report["writes_to_destinations"])

    def test_private_write_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"report.json"
            write_private(p,{"ok":True})
            self.assertEqual(p.stat().st_mode&0o777,0o600)
            with self.assertRaisesRegex(ValueError,"overwrite"):
                write_private(p,{"ok":False})


if __name__=="__main__":
    unittest.main()
