"""Read-only reviewed pilot compilation safety checks."""
import json
import sys
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from commerce_compile_production_pilot import compile_batches, APPROVED_PILOT_IDS


class CompilePilotTests(unittest.TestCase):
    def fixture(self):
        source={"store_id":"95802503","products":[
            {"id":i,"sku":f"SKU-{i}","enabled":True}
            for i in APPROVED_PILOT_IDS]}
        source["products"] += [{"id":1000+i,"sku":f"D-{i}","enabled":False}
                               for i in range(110)]
        plan={"products":[{"mapping":{"external_product_id":str(i)},
                           "source_enabled":True,
                           "item":{"has_variants":False,"parent_sku":None},
                           "content":{"item":f"SKU-{i}","gallery":[]}}
                          for i in APPROVED_PILOT_IDS],
              "errors":[],"source_sha256":"a"*64}
        review={"source_sha256":"a"*64,"currency":"USD",
                "currency_confirmed":True,"selling_price_list":"Standard Selling",
                "draft_only":True,"defer_tax_mapping":True,
                "categories":{"160254004":{"woocommerce_id":16},
                              "160255005":{"woocommerce_id":17},
                              "160277251":{"woocommerce_id":18}},
                "items":{f"SKU-{i}":{} for i in APPROVED_PILOT_IDS}}
        media=[{"url":f"https://cdn.example/{i}.png",
                "sha256":f"{i%11:064x}",
                "erp_file_url":f"/files/{i}.png",
                "woocommerce_media_id":i+1} for i in range(37)]
        return source,plan,review,media

    def test_source_status_drift_fails_closed(self):
        source,plan,review,media=self.fixture()
        source["products"][0]["enabled"]=False
        with self.assertRaisesRegex(ValueError,"source status"):
            compile_batches(source,plan,review,media)

    def test_wrong_price_list_fails_closed(self):
        source,plan,review,media=self.fixture()
        review["selling_price_list"]="Standard Selling USD"
        with self.assertRaisesRegex(ValueError,"price-list"):
            compile_batches(source,plan,review,media)

    def test_missing_image_coverage_fails_closed(self):
        source,plan,review,media=self.fixture()
        with self.assertRaisesRegex(ValueError,"Uploaded media URLs differ"):
            compile_batches(source,plan,review,media)


if __name__=="__main__":
    unittest.main()
