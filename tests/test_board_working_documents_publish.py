"""Regression checks for protected Board Working Documents deployment."""
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "board_working_documents_publish.py"
spec = importlib.util.spec_from_file_location("board_manifest", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class BoardWorkingDocumentsDeploymentTests(unittest.TestCase):
    def test_release_check_stage_promote_replay_and_integrity(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            release = root / "release"
            supplements = root / "supplements"
            release.mkdir()
            supplements.mkdir()
            commit = "a" * 40
            manifest = {
                "schema_version": 1,
                "source": module.SOURCE,
                "source_commit": commit,
                "documents": [{
                    "title": "Religious Role Vocabulary Comparative Analysis",
                    "url": "https://docs.google.com/document/d/1bYaNTo7ok8tnZYkSMF9Uof4b2PoxQkFVy0C5X_XIbH0/edit",
                    "status": "Draft for discussion",
                }],
            }
            approved = (json.dumps(manifest) + "\n").encode()
            (release / "working-documents.json").write_bytes(approved)
            receipt = {
                "source_commit": commit,
                "working_documents_sha256": hashlib.sha256(approved).hexdigest(),
                "working_documents_count": 1,
            }
            (release / "approval.json").write_text(json.dumps(receipt))
            old = b"previous working documents\n"
            target = supplements / "working-documents.json"
            target.write_bytes(old)

            module.run(release, supplements, "check")
            module.run(release, supplements, "stage")
            self.assertEqual(target.read_bytes(), old)

            module.run(release, supplements, "promote")
            self.assertEqual(target.read_bytes(), approved)
            old_sha = hashlib.sha256(old).hexdigest()[:16]
            backup = supplements / f"working-documents.before-{old_sha}.json"
            self.assertEqual(backup.read_bytes(), old)

            module.run(release, supplements, "promote")
            self.assertEqual(target.read_bytes(), approved)

            (release / "working-documents.json").write_bytes(b"tampered")
            with self.assertRaises(ValueError):
                module.run(release, supplements, "promote")
            self.assertEqual(target.read_bytes(), approved)

    def test_legacy_release_does_not_modify_existing_manifest(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            release, supplements = root / "release", root / "supplements"
            release.mkdir()
            supplements.mkdir()
            (release / "approval.json").write_text(json.dumps({"source_commit": "a" * 40}))
            target = supplements / "working-documents.json"
            target.write_text("existing")
            module.run(release, supplements, "promote")
            self.assertEqual(target.read_text(), "existing")


if __name__ == "__main__":
    unittest.main()
