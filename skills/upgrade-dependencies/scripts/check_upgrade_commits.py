"""Check that dependency commits record the bun and uv commands that changed them."""

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

import argparse
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
LOCKS = {"bun.lock": "bun", "uv.lock": "uv"}
MANIFESTS = {"package.json": "bun", "pyproject.toml": "uv"}
FILES = r"`[^`]+`(?:(?:,| and|, and) `[^`]+`)*"
VERB = r"(?:generates|updates)"
COMMAND = re.compile(rf"^`([^`]+)` {VERB} ({FILES})\.$")
HAND_EDIT = re.compile(rf"^A hand edit {VERB} ({FILES}), because \S.*$")
RECORD = re.compile(rf"^(?:`[^`]+` {VERB} |A hand edit\b)")
FORMAT = (
    "write `COMMAND` updates `FILE`. or A hand edit updates `FILE`, because REASON."
)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout


def records(message: str):
    """Return the command lines, the hand edit lines, and malformed record lines."""
    lines: list[str] = []
    for line in message.splitlines()[1:]:
        if lines and lines[-1].startswith("- ") and line.startswith("  "):
            lines[-1] += " " + line.strip()
        else:
            lines.append(line)
    commands, hand_edits, malformed = [], [], []
    for line in lines:
        text = line.removeprefix("- ").strip()
        if not RECORD.match(text):
            continue
        if match := COMMAND.match(text):
            commands.append((match.group(1), re.findall(r"`([^`]+)`", match.group(2))))
        elif match := HAND_EDIT.match(text):
            hand_edits.extend(re.findall(r"`([^`]+)`", match.group(1)))
        else:
            malformed.append(text)
    return commands, hand_edits, malformed


def _runs(command: str, tool: str) -> bool:
    return bool(re.search(rf"(?<![\w./-]){tool}\s", command + " "))


def check_commit(repo: Path, commit: str) -> list[str]:
    parents = _git(repo, "rev-list", "--parents", "-n", "1", commit).split()[1:]
    parent = parents[0] if parents else EMPTY_TREE
    changed = set(
        _git(
            repo, "diff-tree", "--no-commit-id", "--name-only", "-r", parent, commit
        ).splitlines()
    )
    commands, hand_edits, malformed = records(
        _git(repo, "log", "-1", "--format=%B", commit)
    )

    problems = [f"{FORMAT} Found: {line}" for line in malformed]
    written = set()
    for command, paths in commands:
        for path in paths:
            tool = (LOCKS | MANIFESTS).get(PurePosixPath(path).name)
            if tool and not _runs(command, tool):
                problems.append(f"{path}: `{command}` does not run {tool}.")
            written.add(path)
    for path in hand_edits:
        name = PurePosixPath(path).name
        if name in LOCKS:
            problems.append(f"{path}: write a lock with {LOCKS[name]}, not by hand.")
        elif name not in MANIFESTS:
            problems.append(
                f"{path}: omit this hand edit line. No tool owns the file, "
                "so the diff shows the edit."
            )
    for path in sorted(written.union(hand_edits) - changed):
        problems.append(
            f"{path}: the record names it, but the commit does not change it."
        )
    for path in sorted(changed - written):
        name = PurePosixPath(path).name
        if name in LOCKS:
            problems.append(
                f"{path}: name the {LOCKS[name]} command that wrote it, "
                f"as `COMMAND` updates `{path}`."
            )
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("revisions", help="commit range, such as FETCH_HEAD..HEAD")
    parser.add_argument("--repo", type=Path, default=Path("."))
    args = parser.parse_args(argv)

    commits = _git(
        args.repo, "rev-list", "--reverse", "--no-merges", args.revisions
    ).split()
    failed = 0
    for commit in commits:
        if problems := check_commit(args.repo, commit):
            failed += 1
            print(_git(args.repo, "log", "-1", "--format=%h %s", commit).strip())
            for problem in problems:
                print(f"  {problem}")
    print(f"{len(commits)} commits checked, {failed} with record problems.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
