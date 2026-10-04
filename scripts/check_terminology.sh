#!/usr/bin/env bash
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

# Reject vague jargon that hides which property a name refers to. Name the
# property instead, such as current schedule, normalized selector, or compiled
# selector. Tracked and untracked files are checked, and ignored files are not.
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
# Split each term so this script does not match itself.
banned_terms=("canon""ical")
pattern="$(IFS='|'; printf '%s' "${banned_terms[*]}")"

if matches="$(git -C "$ROOT_DIR" grep -n -i -I -E --untracked -e "$pattern" -- . \
  ':!*.lock' ':!*-lock.json')"; then
  echo "Name the specific property instead of these terms:" >&2
  printf '%s\n' "$matches" >&2
  exit 1
else
  status=$?
  # Git returns 1 when no text matches. Report command errors instead of passing.
  if ((status != 1)); then
    exit "$status"
  fi
fi
