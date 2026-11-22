"""Check that the dependency inventory finds pins and flags drift."""

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

# This test is mostly AI generated.

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dependency_inventory

FIXTURE = {
    ".github/workflows/a.yaml": """
jobs:
  test:
    steps:
      - uses: actions/checkout@v4
      - uses: oven-sh/setup-bun@v2
        with:
          bun-version: '1.4.2'
      - uses: astral-sh/setup-uv@v10.4.0
        with:
          version: "0.13.9"
          python-version: "3.12"
""",
    ".github/workflows/b.yaml": """
jobs:
  test:
    strategy:
      matrix:
        python-version: ["3.12"]
    steps:
      - uses: actions/checkout@v5
      - uses: oven-sh/setup-bun@v2
        with:
          bun-version: '1.4.3'
""",
    "docker/Dockerfile.dev": """FROM nvidia/cuopt:26.8.0a-cuda13.3-py3.14
COPY --from=ghcr.io/astral-sh/uv:0.13.9 /uv /bin/
RUN curl -fsSL https://bun.sh/install | bash
RUN curl -fsSL https://deb.nodesource.com/setup_24.x | bash -
""",
    "docker/compose.backend.yml": """services:
  tunnel:
    image: cloudflare/cloudflared:latest
  api:
    image: ${COMPOSE_PROJECT_NAME:-backend}-api:local
""",
    "netlify.toml": """[build.environment]
  NODE_VERSION = "25"
  PYTHON_VERSION = "3.12"
""",
}


class DependencyInventoryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for name, text in FIXTURE.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")

    def test_collects_each_surface_with_locations(self):
        pins = dependency_inventory.collect(self.root)
        values = {(pin.surface, pin.value) for pin in pins}
        self.assertLessEqual(
            {
                ("uv", "0.13.9"),
                ("python", "3.12"),
                ("node (Netlify build)", "25"),
                ("node (dev image CLIs)", "24"),
                ("image nvidia/cuopt", "26.8.0a-cuda13.3-py3.14"),
                ("action astral-sh/setup-uv", "v10.4.0"),
            },
            values,
        )
        self.assertEqual(sum(pin.surface == "uv" for pin in pins), 2)
        self.assertNotIn(
            "image ${COMPOSE_PROJECT_NAME", {pin.surface[:28] for pin in pins}
        )

    def test_conflicts_fail_the_check_and_other_findings_warn(self):
        errors, warnings = dependency_inventory.problems(
            dependency_inventory.collect(self.root)
        )
        self.assertEqual(
            errors,
            [
                "action actions/checkout: conflicting pins v4, v5",
                "bun: conflicting pins 1.4.2, 1.4.3",
            ],
        )
        joined = "\n".join(warnings)
        self.assertIn("bun: unpinned or latest at docker/Dockerfile.dev:3", joined)
        self.assertIn("image cloudflare/cloudflared: unpinned or latest", joined)
        self.assertIn("image nvidia/cuopt: prerelease", joined)
        self.assertIn("Node 25 is not an LTS line", joined)
        self.assertNotIn("dev image CLIs", joined)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(
                dependency_inventory.main(["--root", str(self.root), "--check"]), 1
            )
            self.assertEqual(dependency_inventory.main(["--root", str(self.root)]), 0)

    def test_consistent_pins_pass_the_check(self):
        (self.root / ".github/workflows/b.yaml").unlink()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(
                dependency_inventory.main(["--root", str(self.root), "--check"]), 0
            )


if __name__ == "__main__":
    unittest.main()
