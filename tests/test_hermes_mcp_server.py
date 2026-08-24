import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SERVER = PROJECT_ROOT / "hermes_mcp_server.py"


class HermesMCPServerTests(unittest.TestCase):
    def test_job_status_uses_project_data_when_server_started_elsewhere(self):
        cached_jobs = json.loads((PROJECT_ROOT / "data" / "jobs_cache.json").read_text(encoding="utf-8"))
        expected_count = len(cached_jobs)
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "job_status", "arguments": {}},
        }

        with tempfile.TemporaryDirectory() as foreign_cwd:
            completed = subprocess.run(
                [sys.executable, "-u", str(SERVER)],
                input=json.dumps(request) + "\n",
                text=True,
                capture_output=True,
                cwd=foreign_cwd,
                timeout=10,
                check=True,
            )

        response = json.loads(completed.stdout)
        text = response["result"]["content"][0]["text"]
        self.assertIn(f"Offres en cache : {expected_count}", text)


if __name__ == "__main__":
    unittest.main()
