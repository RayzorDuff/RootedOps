"""Offline safety checks for candidate-only ERPNext image build."""
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/erpnext_image_candidate.sh"


class ERPNextCandidateTests(unittest.TestCase):
    def test_bash_syntax(self):
        subprocess.run(["bash", "-n", str(SCRIPT)], check=True)

    def test_help_does_not_touch_docker(self):
        result = subprocess.run(["bash", str(SCRIPT), "--help"],
                                check=True, text=True, capture_output=True)
        self.assertIn("--build", result.stdout)
        self.assertIn("review-", result.stdout)

    def test_no_production_mutation_paths(self):
        code = SCRIPT.read_text()
        self.assertIn("docker build --pull=false", code)
        self.assertIn("--network none", code)
        self.assertIn("rootedops-erpnext:review-", code)
        self.assertNotIn("docker compose up", code)
        self.assertNotIn("docker volume rm", code)
        self.assertNotIn("docker tag ", code)
        self.assertNotIn("docker compose build", code)

if __name__ == "__main__":
    unittest.main()
