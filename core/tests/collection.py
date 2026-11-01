"""Temporary collection policy during the AI test transition."""

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

import fnmatch
import sys
from pathlib import Path

# Remove with the legacy evaluation suite in the dedicated cleanup branch.
LEGACY_AI_TEST_PATTERNS = [
    "ai_eval",
    "test_ai_eval_*.py",
    "test_ai_ladder_audit.py",
    "test_ai_prefix_cache_probe.py",
    "test_ai_provider_preflight.py",
    "test_ai_read_batch_benchmark.py",
]


def is_legacy_ai_test(selector: str) -> bool:
    path = Path(selector.partition("::")[0])
    return "ai_eval" in path.parts or any(
        fnmatch.fnmatchcase(path.name, pattern) for pattern in LEGACY_AI_TEST_PATTERNS
    )


if __name__ == "__main__":
    # Affected checks pass explicit paths, which bypass pytest discovery ignores.
    for selector in sys.argv[1:]:
        if not is_legacy_ai_test(selector):
            sys.stdout.buffer.write(selector.encode("utf-8") + b"\0")
