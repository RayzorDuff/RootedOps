"""Offline safety checks for one-step remaining 110-product migration."""
import sys
from pathlib import Path
import tempfile
import json
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import commerce_remaining_catalog as bulk


class RemainingCatalogTests(unittest.TestCase):
    def test_unchanged_pilot_exclusion(self):
        self.assertEqual(len(bulk.APPROVED_PILOT_IDS),22)
        self.assertEqual(bulk.SCOPE,"erp.danks.store|shop-test.danks.store")
        self.assertEqual(bulk.SOURCE_SHA,"0b4eec40a1cfd1d62551e2ac951a42dac21984f34ffb2d03f9aea697d1d713a8")

    def test_native_apply_does_not_create_transactions(self):
        self.assertIn("frappe.db.commit()",bulk.ERP_APPLY)
        self.assertIn("frappe.db.rollback()",bulk.ERP_APPLY)
        self.assertIn("import_product(",bulk.ERP_APPLY)
        self.assertIn("'Sales Order'"," ".join(bulk.ERP_APPLY.split()))
        self.assertIn("('Item','Commercial Product Content','Commerce Channel Mapping'",bulk.ERP_VERIFY)
        self.assertNotIn("frappe.db.commit()",bulk.ERP_VERIFY)
        self.assertIn("woocommerce_coming_soon",bulk.WOO_VERIFY)
        self.assertNotIn("wp_insert_post",bulk.WOO_VERIFY)

    def test_fallback_category_preserves_source_metadata(self):
        products=[
            {"source_key":"ecwid:95802503:product:333","source_enabled":False,
             "category_ids":["199701664"],
             "item":{"item_code":"SKU333","has_variants":False,"parent_sku":None},
             "content":{"item":"SKU333","gallery":[],
                        "source_payload":json.dumps({"product":{"enabled":False,"categoryIds":[199701664]}})},
             "woocommerce":{"meta_data":[]},
             "mapping":{"external_product_id":"333"}}]
        planned={"source_sha256":"testhash","products":products,"errors":[]}
        with patch.object(bulk,"compile_catalog") as compiler:
            compiler.return_value={"records":[{"mapping":{"external_product_id":"333"},
                "source_key":"ecwid:95802503:product:333","price":None,
                "parent_sku":None,"item":{"has_variants":False},
                "woocommerce":{"regular_price":"","status":"draft"}}]}
            with self.assertRaisesRegex(ValueError,"Compiled full remaining catalog count drift"):
                bulk.build_records(planned,products,{},71)
            args=compiler.call_args
            selected,review=args.args[:2]
            self.assertEqual(selected['products'][0]['category_ids'],['__rootedops_uncategorized__'])
            self.assertEqual(review['categories']['__rootedops_uncategorized__']['woocommerce_id'],71)
            self.assertEqual(review['items']['SKU333']['item_code'],'SKU333')
            self.assertTrue(review['include_disabled_drafts'])
            self.assertTrue(review['allow_unpriced_drafts'])
            metadata=selected['products'][0]['woocommerce']['meta_data']
            self.assertEqual(metadata[0]['key'],'_rootedops_original_ecwid_categories')

    def test_rejects_changed_source_before_uses_docker(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"source.json"
            path.write_text('{"store_id":"95802503","products":[]}')
            with self.assertRaisesRegex(ValueError,"snapshot checksum drift"):
                bulk.read_source(path)

    def test_verifier_requires_all_110_records(self):
        with patch.object(bulk,"run_json") as call:
            call.side_effect=[
                {"checked":109,"counts":{}},
                {"records":[],"drafts":132,"published":0}]
            with self.assertRaisesRegex(ValueError,"reconciliation count drift"):
                bulk.reconcile(Path("/tmp"),[],{"woo_done":{}})

if __name__=="__main__":
    unittest.main()
