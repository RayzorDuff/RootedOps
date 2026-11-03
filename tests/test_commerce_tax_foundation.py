"""Focused offline checks for ERPNext native Colorado component staging."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import commerce_tax_foundation as foundation

class TaxFoundationTests(unittest.TestCase):
    def test_embedded_frappe_python_compiles(self):
        compile(foundation.ERP,"<tax-foundation>","exec")

    def test_verified_component_rates_and_safety(self):
        code=foundation.ERP
        self.assertIn('"CO State 2.9% Component - Incomplete",2.9',code)
        self.assertIn('"CO Johnstown 3.5% Component - Incomplete",3.5',code)
        self.assertIn('"disabled":1,"is_default":0',code)
        self.assertIn('legacy.is_default=0',code)
        self.assertIn('assert not current',code)
        self.assertIn('frappe.db.rollback()',code)
        self.assertIn('assert before==after',code)
        self.assertIn('frappe.db.commit()',code)
        self.assertNotIn('new Sales Invoice',code)
        self.assertNotIn('doc.submit()',code)
        self.assertNotIn('frappe.db.set_value("Item"',code)

    def test_missing_deployment_rejects_without_execution(self):
        with patch.object(foundation.subprocess,"run") as call:
            with self.assertRaisesRegex(ValueError,"Installed RootedOps"):
                foundation.run(Path("/missing-rootedops-tax"),False)
            call.assert_not_called()

    def test_native_failure_propagates_without_retry(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/".env").touch()
            (root/"docker").mkdir()
            (root/"docker/docker-compose.yml").touch()
            with patch.object(foundation.subprocess,"run") as call:
                call.return_value.returncode=1
                call.return_value.stderr="Template refused"
                with self.assertRaisesRegex(RuntimeError,"Template refused"):
                    foundation.run(root,True)
                call.assert_called_once()

if __name__=="__main__":
    unittest.main()
