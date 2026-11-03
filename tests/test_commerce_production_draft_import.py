"""Offline fail-closed tests for the production-native draft import runner."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import commerce_production_draft_import as importer


class DraftImportTests(unittest.TestCase):
    def test_native_contract(self):
        erp=importer.ERP_SCRIPT
        woo=importer.WOO_SCRIPT
        self.assertIn("frappe.init(site='erp.danks.store')",erp)
        self.assertIn("frappe.db.rollback()",erp)
        self.assertIn("import_product(payload)",erp)
        self.assertIn("frappe.db.commit()",erp)
        self.assertIn("'Sales Invoice'"," ".join(erp.split()))
        self.assertIn("wc_get_product_id_by_sku",woo)
        self.assertIn("get_meta('_rootedops_source_key'",woo)
        self.assertIn("set_status('draft')",woo)
        self.assertIn("set_stock_quantity(0)",woo)
        self.assertIn("set_catalog_visibility('hidden')",woo)
        self.assertIn("set_tax_status('none')",woo)
        self.assertNotIn("wp_publish_post",woo)
        self.assertNotIn("payment_complete",woo)

    def test_compiled_hash_fails_before_live_contact(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"batch.json"
            path.write_text(json.dumps({"records":[]}))
            with self.assertRaises(ValueError):
                importer.verify_compiled(path,importer.FIRST_BATCH_SHA)

    def test_all_approved_batch_ids_and_counts(self):
        expected=[5,5,5,5,2]
        self.assertEqual([len(importer.BATCHES[n][1]) for n in range(1,6)],expected)
        self.assertEqual(len(set().union(*(ids for _,ids in importer.BATCHES.values()))),22)
        for n,(sha,ids) in importer.BATCHES.items():
            number,actual=importer.batch_for_sha(sha)
            self.assertEqual((number,actual),(n,ids))
        with self.assertRaisesRegex(ValueError,"approved pilot batch SHA"):
            importer.batch_for_sha("a"*64)

    def test_batch_two_requires_first_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"pilot-02-import-receipt.json"
            with self.assertRaisesRegex(ValueError,"Prior pilot import receipt missing"):
                importer.require_prior_receipts(2,path)

    def test_json_native_failure_is_not_suppressed(self):
        with patch.object(importer.subprocess,"run") as run:
            run.return_value.returncode=1
            run.return_value.stderr="refused"
            with self.assertRaisesRegex(RuntimeError,"refused"):
                importer.run_json(["docker"],{},"ERPNext")

    def test_readonly_does_not_enter_write_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/".env").write_text("")
            (root/"docker").mkdir()
            (root/"docker/docker-compose.yml").write_text("")
            receipt=root/"pilot-01-import-receipt.json"
            with patch.object(importer,"verify_compiled",return_value=[{"source_key":str(i),"woocommerce":{"sku":str(i)}} for i in range(5)]),\
                 patch.object(importer,"guard_live") as guard,\
                 patch.object(importer,"run_json") as request:
                output=importer.import_batch(root,root/"batch.json",importer.FIRST_BATCH_SHA,receipt,False)
                self.assertFalse(output["writes"])
                guard.assert_called_once_with(root)
                request.assert_not_called()
                self.assertFalse(receipt.exists())

    def test_rejects_receipt_scope_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/".env").write_text("")
            (root/"docker").mkdir()
            (root/"docker/docker-compose.yml").write_text("")
            receipt=root/"pilot-01-import-receipt.json"
            receipt.write_text(json.dumps({"scope":"wrong","compiled_sha256":importer.FIRST_BATCH_SHA}))
            with patch.object(importer,"verify_compiled",return_value=[{"source_key":str(i)} for i in range(5)]),\
                 patch.object(importer,"guard_live") as guard:
                with self.assertRaisesRegex(ValueError,"scope/hash drift"):
                    importer.import_batch(root,root/"batch.json",importer.FIRST_BATCH_SHA,receipt,False)
                guard.assert_not_called()


if __name__=="__main__":
    unittest.main()
