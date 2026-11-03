"""Offline controls for editing canonical commerce records from ERPNext Item.

Native Frappe browser/database acceptance still required on isolated test2.
"""
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "erpnext/apps/rootedops_commerce/rootedops_commerce"


class ItemEditorialTests(unittest.TestCase):
    def test_backend_code_compiles(self):
        for file in (
            APP / "item_editorial.py",
            APP / "setup.py",
            APP / "rootedops_commerce/doctype/commercial_product_content/commercial_product_content.py",
        ):
            compile(file.read_text(), str(file), "exec")

    def test_js_syntax(self):
        js = APP / "public/js/item_commerce.js"
        result = subprocess.run(["node", "--check", str(js)], capture_output=True, text=True)
        if result.returncode == 127:
            self.skipTest("Node.js unavailable")
        self.assertEqual(0, result.returncode, result.stderr)

    def test_editorial_single_authority_and_permissions(self):
        backend = (APP / "item_editorial.py").read_text()
        self.assertIn('frappe.get_doc("Commercial Product Content", item)', backend)
        self.assertIn('erp.check_permission("write")', backend)
        self.assertIn('doc.check_permission("write")', backend)
        self.assertIn('str(doc.modified) != str(expected_modified)', backend)
        self.assertIn('set(values) != set(EDITORIAL_FIELDS)', backend)
        self.assertIn('doc.save()', backend)
        self.assertIn('"woo_synchronized": False', backend)
        self.assertNotIn("requests.post(", backend)

    def test_item_projection_checks_prior_source_state(self):
        code = (APP / "rootedops_commerce/doctype/commercial_product_content/commercial_product_content.py").read_text()
        self.assertIn("self.get_doc_before_save()", code)
        self.assertIn('item.check_permission("write")', code)
        self.assertIn('previous.full_description', code)
        self.assertIn('previous.public_title', code)
        self.assertIn('item.save()', code)

    def test_item_fields_are_read_only_preview_not_duplicate_authority(self):
        code = (APP / "setup.py").read_text()
        self.assertIn('"rootedops_commerce_preview"', code)
        self.assertIn('"fieldtype": "HTML"', code)
        self.assertIn('"read_only": 1', code)
        self.assertNotIn('"seo_title",', code)
        hook = (APP / "hooks.py").read_text()
        self.assertIn('doctype_js = {"Item": "public/js/item_commerce.js"}', hook)
        self.assertIn("after_migrate", hook)

    def test_ui_has_edit_and_full_content_actions(self):
        js = (APP / "public/js/item_commerce.js").read_text()
        self.assertIn("Edit Commerce Content", js)
        self.assertIn("Open Full Commerce Record", js)
        self.assertIn("save_item_editorial", js)
        self.assertIn("source_key", js)
        self.assertIn("seo_title", js)
        self.assertIn("gallery", js)
        self.assertIn("channel_overrides", js)
        self.assertNotIn("woocommerce", js.lower().split('method: "rootedops_commerce.item_editorial.save_item_editorial"')[0].split('refresh(frm)')[0])


if __name__ == "__main__":
    unittest.main()
