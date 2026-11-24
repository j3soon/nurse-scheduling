"""Check that the commit record check finds missing commands and needless hand edit lines."""

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

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_upgrade_commits

WORKFLOW = "jobs:\n  a:\n    steps:\n      - uses: actions/checkout@{}\n"
PACKAGE = '{{"scripts": {{"dev": "{}"}}, "dependencies": {{"left-pad": "{}"}}}}\n'


class CheckUpgradeCommitsTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.repo = Path(temporary.name)
        self.git("init", "-q")
        self.git("config", "--local", "user.name", "Upgrade Test")
        self.git("config", "--local", "user.email", "upgrade-test@example.invalid")
        self.commit(
            "chore: add the base files",
            {
                "web-frontend/package.json": PACKAGE.format("next", "1.0.0"),
                "web-frontend/bun.lock": "left-pad@1.0.0\n",
                ".github/workflows/a.yaml": WORKFLOW.format("v4"),
            },
        )

    def git(self, *args):
        return subprocess.run(
            ["git", "-C", str(self.repo), *args],
            check=True,
            capture_output=True,
            text=True,
        ).stdout

    def commit(self, message, files):
        for path, text in files.items():
            target = self.repo / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)
        return self.git("rev-parse", "HEAD").strip()

    def problems(self, message, files):
        commit = self.commit(message, files)
        return check_upgrade_commits.check_commit(self.repo, commit)

    def bump_left_pad(self, record, version="1.1.0"):
        return self.problems(
            f"fix: upgrade left-pad\n\n{record}",
            {
                "web-frontend/package.json": PACKAGE.format("next", version),
                "web-frontend/bun.lock": f"left-pad@{version}\n",
            },
        )

    def test_one_command_needs_one_line(self):
        record = (
            "`cd web-frontend && bun add --exact left-pad@1.1.0` updates "
            "`web-frontend/package.json` and `web-frontend/bun.lock`."
        )
        self.assertEqual(self.bump_left_pad(record), [])

    def test_several_commands_use_bullets(self):
        record = (
            "- `cd web-frontend && bun pm pkg set dependencies.left-pad=1.1.0` "
            "updates `web-frontend/package.json`.\n"
            "- `cd web-frontend && bun install` updates `web-frontend/bun.lock`."
        )
        self.assertEqual(self.bump_left_pad(record), [])

    def test_lock_needs_a_tool_command(self):
        record = (
            "A hand edit updates `web-frontend/package.json`, because no bun "
            "command writes this field."
        )
        problems = self.bump_left_pad(record)
        self.assertEqual(len(problems), 1)
        self.assertIn("web-frontend/bun.lock: name the bun command", problems[0])

    def test_record_lines_need_files_a_reason_and_changed_files(self):
        record = (
            "- `cd web-frontend && bun install` updates the lock.\n"
            "- A hand edit updates `web-frontend/package.json`.\n"
            "- `cd web-frontend && uv lock` updates `web-frontend/bun.lock`.\n"
            "- `cd web-frontend && bun install` updates `web-frontend/bun.lockb`."
        )
        problems = self.bump_left_pad(record)
        self.assertEqual(len(problems), 4)
        self.assertIn(
            "Found: `cd web-frontend && bun install` updates the", problems[0]
        )
        self.assertIn("Found: A hand edit updates", problems[1])
        self.assertIn("does not run bun", problems[2])
        self.assertIn("bun.lockb: the record names it, but the commit", problems[3])

    def test_hand_edits_of_files_no_tool_owns_need_no_record(self):
        workflow = {".github/workflows/a.yaml": WORKFLOW.format("v7")}
        self.assertEqual(self.problems("ci: upgrade checkout", workflow), [])
        problems = self.problems(
            "ci: upgrade checkout\n\nA hand edit updates "
            "`.github/workflows/a.yaml`, because no tool writes action tags.",
            {".github/workflows/a.yaml": WORKFLOW.format("v8")},
        )
        self.assertEqual(len(problems), 1)
        self.assertIn("omit this hand edit line", problems[0])

    def test_unchanged_locks_need_no_record(self):
        problems = self.problems(
            "chore: change the dev script",
            {"web-frontend/package.json": PACKAGE.format("next dev", "1.0.0")},
        )
        self.assertEqual(problems, [])


if __name__ == "__main__":
    unittest.main()
