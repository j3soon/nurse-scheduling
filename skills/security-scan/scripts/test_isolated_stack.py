"""Check scan process configuration without starting backend services."""

# This file is part of Nurse Scheduling Project, see <https://github.com/j3soon/nurse-scheduling>.
#
# Copyright (C) 2023-2026 Johnson Sun
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

# This file is mostly AI generated.

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("isolated_stack.sh")
REPO_ROOT = SCRIPT.parents[3]


class IsolatedStackTests(unittest.TestCase):
    """Capture the environment passed to each service through executable stand-ins."""

    def setUp(self) -> None:
        artifacts = REPO_ROOT / "artifacts/security-scan"
        artifacts.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=artifacts)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        python = self.bin / "python"
        python.write_text(
            f"#!{sys.executable}\n"
            "import json, os, sys\n"
            "if len(sys.argv) > 1 and sys.argv[1] in ('-c', '-'):\n"
            f"    os.execv({sys.executable!r}, [{sys.executable!r}, *sys.argv[1:]])\n"
            "print(json.dumps(dict(os.environ)), flush=True)\n"
        )
        python.chmod(0o755)
        curl = self.bin / "curl"
        curl.write_text("#!/bin/sh\nexit 0\n")
        curl.chmod(0o755)
        self.environment = {
            "PATH": f"{self.bin}{os.pathsep}{os.defpath}",
            "HOME": str(self.root),
            "LANG": "C.UTF-8",
            "SECURITY_SCAN_STATE_DIR": str(self.root / "stack"),
            "AI_HISTORY_POSTGRES_URL": "postgresql://deployment.invalid/history",
            "JOB_REDIS_URL": "redis://deployment.invalid/0",
            "API_AUTH_TOKEN": "deployment-api-key",
            "API_AUTH_TOKENS": '{"operator": "deployment-api-key"}',
            "AI_AUTH_TOKENS": '{"operator": "deployment-ai-key"}',
            "AI_OPTIMIZER_AUTH_TOKEN": "deployment-optimizer-key",
            "HTTP_PROXY": "http://deployment.invalid:3128",
            "SENTRY_DSN": "https://deployment.invalid/sentry",
        }

    def start(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(SCRIPT), "start", str(REPO_ROOT)],
            env=self.environment,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

    def service_environments(self) -> dict[str, dict[str, str]]:
        pending = {name: self.root / "stack" / f"{name}.log" for name in ("provider", "api-open", "api-keyed", "ai")}
        captured = {}
        deadline = time.monotonic() + 5
        while pending and time.monotonic() < deadline:
            for name, path in list(pending.items()):
                try:
                    captured[name] = json.loads(path.read_text())
                except (FileNotFoundError, json.JSONDecodeError):
                    continue
                del pending[name]
            if pending:
                time.sleep(0.01)
        self.assertFalse(pending, f"Services did not record their environment: {pending}")
        return captured

    def test_deployment_settings_do_not_reach_scan_services(self) -> None:
        result = self.start()
        self.assertEqual(result.returncode, 0, result.stderr)
        services = self.service_environments()
        for name, environment in services.items():
            with self.subTest(service=name):
                for key in self.environment.keys() - {
                    "PATH",
                    "HOME",
                    "LANG",
                    "API_AUTH_TOKEN",
                    "JOB_REDIS_URL",
                }:
                    self.assertNotIn(key, environment)
                self.assertNotEqual(environment.get("API_AUTH_TOKEN"), "deployment-api-key")
                self.assertNotEqual(environment.get("JOB_REDIS_URL"), self.environment["JOB_REDIS_URL"])
        self.assertEqual(services["api-open"]["JOB_BACKEND"], "memory")
        self.assertEqual(services["api-keyed"]["JOB_BACKEND"], "memory")

    def test_redis_requires_an_explicit_loopback_url_and_fresh_namespace(self) -> None:
        self.environment["SECURITY_SCAN_REDIS_URL"] = "redis://127.0.0.1:26391/0"
        prefixes = []
        for _ in range(2):
            result = self.start()
            self.assertEqual(result.returncode, 0, result.stderr)
            services = self.service_environments()
            for name in ("api-open", "api-keyed"):
                self.assertEqual(services[name]["JOB_BACKEND"], "redis")
                self.assertEqual(
                    services[name]["JOB_REDIS_URL"],
                    self.environment["SECURITY_SCAN_REDIS_URL"],
                )
            self.assertNotEqual(
                services["api-open"]["JOB_REDIS_KEY_PREFIX"],
                services["api-keyed"]["JOB_REDIS_KEY_PREFIX"],
            )
            prefixes.append(services["api-open"]["JOB_REDIS_KEY_PREFIX"])
        self.assertNotEqual(*prefixes)

    def test_remote_redis_is_rejected_before_starting_services(self) -> None:
        self.environment["SECURITY_SCAN_REDIS_URL"] = "redis://deployment.invalid/0"
        result = self.start()
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("SECURITY_SCAN_REDIS_URL", result.stderr)
        self.assertFalse(list((self.root / "stack").glob("*.pid")))


if __name__ == "__main__":
    unittest.main()
