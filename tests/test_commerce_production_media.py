"""Offline media-runner contracts: never invoke Docker or network."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"integrations/commerce"))
spec=importlib.util.spec_from_file_location("production_media",
    ROOT/"scripts/commerce_production_media.py")
media=importlib.util.module_from_spec(spec)
spec.loader.exec_module(media)


class ProductionMediaTests(unittest.TestCase):
    def test_rejects_wrong_manifest_checksum_before_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            path=root/"manifest.json"
            path.write_text("[]")
            with self.assertRaisesRegex(ValueError,"Manifest SHA256 mismatch"):
                media.preflight(path,root,"0"*64)

    def test_rejects_insufficient_manifest_coverage(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            path=root/"manifest.json"
            raw=b"[]"
            path.write_bytes(raw)
            with self.assertRaisesRegex(ValueError,"Expected 37 unique"):
                media.preflight(path,root,hashlib.sha256(raw).hexdigest())

    def test_archive_verifier_is_shared(self):
        self.assertIsNotNone(media.verified_blob)
        self.assertEqual(media.ERP_SITE,"erp.danks.store")
        self.assertEqual(media.SHOP,"dank-store-test-dank-wordpress-1")
        self.assertIn("frappe.init(site='erp.danks.store')",media.ERP_PY)
        self.assertIn("woocommerce_coming_soon",media.WP_PHP)


if __name__=="__main__":
    unittest.main()
