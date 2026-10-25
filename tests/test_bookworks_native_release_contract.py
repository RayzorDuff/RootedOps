"""Static safety-contract tests for the WordPress-native publishing boundary.

Run: python3 -m unittest discover -s tests -p 'test_bookworks_native_release_contract.py'
PHP and Bash syntax checks are performed when those executables are available.
WordPress integration tests still require a disposable WordPress database.
"""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]

class NativeReleaseContract(unittest.TestCase):
    def test_shell_syntax(self):
        if not shutil.which("bash"):
            self.skipTest("bash unavailable")
        for name in ("promote_bookworks_native.sh", "check_bookworks_native_release.sh",
                     "convert_bookworks_original_draft.sh", "deploy_bookworks_artifact.sh"):
            with self.subTest(name=name):
                subprocess.run(["bash", "-n", str(ROOT / "scripts" / name)], check=True)

    def test_php_syntax(self):
        if not shutil.which("php"):
            self.skipTest("PHP unavailable")
        for name in ("promote_bookworks_native.php", "check_bookworks_native_release.php",
                     "convert_bookworks_original_draft.php", "import_bookworks_publication.php"):
            with self.subTest(name=name):
                subprocess.run(["php", "-l", str(ROOT / "scripts" / name)],
                               check=True, capture_output=True)

    def test_promotion_requires_approved_release_and_managed_page(self):
        shell = (ROOT / "scripts/promote_bookworks_native.sh").read_text()
        php = (ROOT / "scripts/promote_bookworks_native.php").read_text()
        self.assertIn('deploy_bookworks_artifact.sh', shell)
        self.assertIn('check_bookworks_native_release.sh', shell)
        self.assertIn("'_bookworks_publication_key'", php)
        self.assertIn("'_bookworks_managed_html_sha256'", php)
        self.assertIn("'_bookworks_native_release_history'", php)
        self.assertIn("Already published; use reviewed update workflow", php)
        self.assertIn("Unknown rollback snapshot", php)
        self.assertIn("wp_update_post", php)

    def test_fundraising_widgets_remain_outside_managed_content(self):
        php = (ROOT / "wordpress/bookworks-fundraising-loader.php").read_text()
        self.assertIn("add_filter('the_content'", php)
        self.assertIn("rootedops_bookworks_fundraising_campaigns", php)
        self.assertNotIn("update_post_meta($post->ID, '_bookworks_managed_html_sha256'", php)

if __name__ == "__main__":
    unittest.main()
