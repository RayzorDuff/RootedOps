"""Offline guard checks for stopping only explicitly identified test2 projects."""
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/stop_shared_test2.sh"


class Test2StopGuards(unittest.TestCase):
    def test_bash_syntax(self):
        subprocess.run(["bash", "-n", str(SCRIPT)], check=True)

    def test_help_does_not_touch_docker(self):
        r = subprocess.run(["bash", str(SCRIPT), "--help"],
                           text=True, capture_output=True, check=True)
        self.assertIn("--confirm-shared-test2", r.stdout)

    def test_no_production_or_destructive_paths(self):
        code = SCRIPT.read_text()
        self.assertIn(".test-deployment/TEST_ENVIRONMENT", code)
        self.assertIn('rootedops-full-test', code)
        self.assertIn('dank-store-test', code)
        self.assertIn('label=com.docker.compose.project=', code)
        for forbidden in ("docker compose down", "docker volume rm", "docker rm ",
                          "docker system prune", "docker image prune"):
            self.assertNotIn(forbidden, code)


if __name__ == "__main__":
    unittest.main()
