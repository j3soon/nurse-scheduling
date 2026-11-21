"""Check that agent worktrees stay isolated and survive a changed mount path."""

# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Johnson Sun
# This test is mostly AI generated.

import os
import shutil
import subprocess
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HELPER = ROOT / "scripts/add_worktree.sh"


class AgentWorktreeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "host checkout"
        self.root.mkdir()
        self.git("init", "-q")
        self.git("config", "--local", "user.name", "Worktree Test")
        self.git("config", "--local", "user.email", "worktree-test@example.invalid")
        (self.root / ".gitignore").write_text("/.worktrees/\n", encoding="utf-8")
        (self.root / "shared.txt").write_text("original\n", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-qm", "Seed worktree fixture")

    def git(self, *args, cwd=None):
        return subprocess.check_output(
            ["git", "-C", str(cwd or self.root), *args],
            text=True,
            stderr=subprocess.PIPE,
            timeout=20,
        ).strip()

    def add(self, *args, cwd=None, env=None):
        return subprocess.run(
            ["bash", str(HELPER), *args],
            cwd=cwd or self.root,
            env=env,
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )

    def test_parallel_checkouts_survive_a_different_mount_path(self):
        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(self.add, ["feat/shared", "fix/shared"]))
        for result in results:
            self.assertEqual(result.returncode, 0, result.stderr)
        feature = self.root / ".worktrees/feat/shared"
        fix = self.root / ".worktrees/fix/shared"
        (feature / "shared.txt").write_text("feature change\n", encoding="utf-8")
        self.assertEqual((fix / "shared.txt").read_text(encoding="utf-8"), "original\n")
        self.assertEqual(self.git("status", "--porcelain"), "")
        for path in (feature, fix):
            gitdir = (
                (path / ".git")
                .read_text(encoding="utf-8")
                .removeprefix("gitdir: ")
                .strip()
            )
            self.assertFalse(Path(gitdir).is_absolute())
        relocated = self.root.with_name("container mount")
        self.root.rename(relocated)
        self.root = relocated
        feature = self.root / ".worktrees/feat/shared"
        fix = self.root / ".worktrees/fix/shared"
        self.assertEqual(self.git("branch", "--show-current", cwd=feature), "feat/shared")
        self.assertEqual(self.git("branch", "--show-current", cwd=fix), "fix/shared")
        self.git("add", "shared.txt", cwd=feature)
        self.git("commit", "-qm", "Independent agent change", cwd=feature)
        self.assertEqual(self.git("status", "--porcelain"), "")
        listing = self.git("worktree", "list", "--porcelain")
        self.assertNotIn("prunable", listing)
        self.git("worktree", "remove", str(feature))
        self.git("worktree", "remove", str(fix))

    def test_invalid_names_refs_and_existing_content_are_preserved(self):
        for name in (
            "../outside",
            "fix/nested/path",
            "fix/..",
            "bare-name",
            "agent/legacy",
            "j3soon/legacy",
        ):
            self.assertNotEqual(self.add(name).returncode, 0, name)
        self.assertNotEqual(self.add("fix/bad-base", "does-not-exist").returncode, 0)
        occupied = self.root / ".worktrees/fix/occupied"
        occupied.mkdir(parents=True)
        (occupied / "keep.txt").write_text("keep", encoding="utf-8")
        self.assertNotEqual(self.add("fix/occupied").returncode, 0)
        self.assertEqual((occupied / "keep.txt").read_text(encoding="utf-8"), "keep")
        self.git("branch", "fix/existing")
        self.assertNotEqual(self.add("fix/existing").returncode, 0)
        self.assertFalse((self.root / ".worktrees/fix/existing").exists())
        self.assertEqual(self.git("branch", "--list", "fix/bad-base"), "")

    def test_existing_flat_worktree_cannot_be_a_type_directory(self):
        legacy = self.root / ".worktrees/docs"
        self.git("worktree", "add", "--relative-paths", "-b", "docs/legacy", str(legacy))
        result = self.add("docs/nested")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("already contains a checkout", result.stderr)
        self.assertFalse((legacy / "nested").exists())
        self.assertEqual(self.git("branch", "--list", "docs/nested"), "")

    def test_linked_checkout_cannot_hide_git_metadata_outside_the_mount(self):
        self.assertEqual(self.add("feat/first").returncode, 0)
        checkout = self.root / ".worktrees/feat/first"
        result = self.add("fix/nested", cwd=checkout)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("main clone", result.stderr)
        self.assertFalse((checkout / ".worktrees").exists())

    def test_old_git_fails_before_creating_a_worktree(self):
        shim_dir = Path(self.temporary.name) / "bin"
        shim_dir.mkdir()
        shim = shim_dir / "git"
        shim.write_text(
            '#!/bin/sh\nif [ "$*" = "worktree add -h" ]; then echo "old Git help"; exit 129; fi\n'
            'exec "$WORKTREE_TEST_REAL_GIT" "$@"\n',
            encoding="utf-8",
        )
        shim.chmod(0o755)
        result = self.add(
            "fix/old",
            env={
                **os.environ,
                "PATH": f"{shim_dir}{os.pathsep}{os.environ['PATH']}",
                "WORKTREE_TEST_REAL_GIT": shutil.which("git"),
            },
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Git 2.48+", result.stderr)
        self.assertFalse((self.root / ".worktrees").exists())


if __name__ == "__main__":
    unittest.main()
