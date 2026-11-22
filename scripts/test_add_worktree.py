"""Check that agent worktrees stay isolated, survive a changed mount path, and keep staging settings."""

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
REMOVER = ROOT / "scripts/remove_worktree.sh"


class AgentWorktreeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "host checkout"
        self.root.mkdir()
        self.git("init", "-q")
        self.git("config", "--local", "user.name", "Worktree Test")
        self.git("config", "--local", "user.email", "worktree-test@example.invalid")
        (self.root / ".gitignore").write_text("/.worktrees/\n.env.*\n", encoding="utf-8")
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
        return self.run_script(HELPER, *args, cwd=cwd, env=env)

    def remove(self, *args):
        return self.run_script(REMOVER, *args)

    def run_script(self, script, *args, cwd=None, env=None):
        return subprocess.run(
            ["bash", str(script), *args],
            cwd=cwd or self.root,
            env=env,
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )

    def write_staging_env(self, root, text):
        path = root / "docker/.env.staging"
        path.parent.mkdir(exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

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

    def test_new_checkout_receives_the_staging_env_file(self):
        self.write_staging_env(self.root, "API_TOKEN=main\n")
        self.assertEqual(self.add("feat/env").returncode, 0)
        checkout = self.root / ".worktrees/feat/env"
        self.assertEqual((checkout / "docker/.env.staging").read_text(encoding="utf-8"), "API_TOKEN=main\n")
        self.assertEqual(self.git("status", "--porcelain", cwd=checkout), "")

    def test_remove_requires_every_branch_commit_in_the_base(self):
        self.git("branch", "dev")
        self.assertEqual(self.add("fix/merge").returncode, 0)
        checkout = self.root / ".worktrees/fix/merge"
        (checkout / "shared.txt").write_text("fix\n", encoding="utf-8")
        self.git("commit", "-qam", "Unmerged fix", cwd=checkout)
        result = self.remove("fix/merge")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("Unmerged fix", result.stderr)
        self.assertTrue(checkout.exists())
        self.git("branch", "-f", "dev", "fix/merge")
        result = self.remove("fix/merge")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(checkout.parent.exists())

    def test_remove_waits_for_a_decision_on_a_changed_staging_env(self):
        self.git("branch", "dev")
        main_env = self.write_staging_env(self.root, "KEEP=1\nTOKEN=old-secret\nDROP=1\n")
        changed = "KEEP=1\nTOKEN=new-secret\nADDED=1\n"
        for name in ("fix/keep", "fix/update"):
            self.assertEqual(self.add(name).returncode, 0)
            self.write_staging_env(self.root / ".worktrees" / name, changed)
        result = self.remove("fix/keep")
        self.assertEqual(result.returncode, 3, result.stderr)
        for line in ("added: ADDED", "removed: DROP", "changed: TOKEN"):
            self.assertIn(line, result.stderr)
        self.assertNotIn("secret", result.stdout + result.stderr)
        self.assertTrue((self.root / ".worktrees/fix/keep").exists())
        self.assertEqual(self.remove("fix/keep", "--keep-env-staging").returncode, 0)
        self.assertIn("TOKEN=old-secret", main_env.read_text(encoding="utf-8"))
        self.assertEqual(self.remove("fix/update", "--update-env-staging").returncode, 0)
        self.assertEqual(main_env.read_text(encoding="utf-8"), changed)

    def test_remove_keeps_a_main_staging_env_changed_after_the_copy(self):
        self.git("branch", "dev")
        main_env = self.write_staging_env(self.root, "TOKEN=old\n")
        self.assertEqual(self.add("fix/stale").returncode, 0)
        main_env.write_text("TOKEN=rotated\n", encoding="utf-8")
        result = self.remove("fix/stale")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Only the main clone changed", result.stdout)
        self.assertEqual(main_env.read_text(encoding="utf-8"), "TOKEN=rotated\n")


if __name__ == "__main__":
    unittest.main()
