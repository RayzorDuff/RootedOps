"""Regression checks for published-page lifecycle guardrails.

These are source-level contracts, not substitutes for an integration test against
a disposable WordPress container with a populated database.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SHELL = (ROOT / "scripts/promote_bookworks_original_html.sh").read_text()
PHP = (ROOT / "scripts/promote_bookworks_original_html.php").read_text()
STAGE = (ROOT / "scripts/deploy_bookworks_original_html.sh").read_text()


class BookWorksPublishedPageContract(unittest.TestCase):
    def test_promote_requires_approved_release_validation(self):
        self.assertIn('deploy_bookworks_original_html.sh', SHELL)
        self.assertIn('--mode check', SHELL)
        self.assertIn('original-html', STAGE)
        self.assertIn('original_html_sha256', STAGE)

    def test_draft_stage_guard_retained(self):
        self.assertIn('Managed page is not a draft; refusing live HTML replacement', STAGE)

    def test_promote_preserves_wordpress_page(self):
        self.assertIn("get_page_by_path($slug", PHP)
        self.assertIn("post_status !== 'publish'", PHP)
        self.assertIn("post_content) !== $expected", PHP)
        self.assertIn("Managed key conflict", PHP)
        self.assertNotIn('wp_insert_post(', PHP)
        self.assertNotIn('wp_delete_post(', PHP)

    def test_adoption_ignores_only_trashed_predecessors(self):
        self.assertIn("['trash', 'auto-draft']", PHP)
        self.assertIn("active_matches", PHP)

    def test_promotion_is_backed_up_and_atomic(self):
        self.assertIn('cp -n "$REMOTE"', SHELL)
        self.assertIn('Backup checksum mismatch', SHELL)
        self.assertIn('Temporary HTML checksum mismatch', SHELL)
        self.assertIn('mv -f "$TMP" "$REMOTE"', SHELL)

    def test_rollback_selects_verified_archived_checksum(self):
        self.assertIn('--to-sha', SHELL)
        self.assertIn('No archived HTML with requested checksum', SHELL)
        self.assertIn('Archived HTML checksum mismatch', SHELL)
        self.assertIn('record', SHELL)


if __name__ == "__main__":
    unittest.main()
