#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Johnson Sun
# This file is mostly AI generated.

set -euo pipefail

if [[ ${1:-} == --help ]]; then
  echo 'Usage: scripts/add_worktree.sh TYPE/NAME [BASE_REF]'
  echo 'Create a branch such as fix/api in .worktrees/fix/api using relative Git paths (Git 2.48+).'
  exit 0
fi
if (($# < 1 || $# > 2)) ||
  [[ ! $1 =~ ^[a-z][a-z0-9-]*/[A-Za-z0-9][A-Za-z0-9._-]*$ || $1 == agent/* || $1 == j3soon/* ]]; then
  echo 'Provide a branch with a change-type prefix, such as fix/api or feat/ui.' >&2
  exit 2
fi

root_dir="$(git rev-parse --show-toplevel)"
if [[ ! -d "$root_dir/.git" ]]; then
  echo 'Run from the main clone so .git and .worktrees are inside the same Docker mount.' >&2
  exit 2
fi
help_text="$(git worktree add -h 2>&1 || true)"
if [[ $help_text != *relative-paths* ]]; then
  echo 'This workflow needs Git 2.48+ on the host and in the container. Rebuild older dev images.' >&2
  exit 2
fi

branch="$1"
base_ref="${2:-HEAD}"
worktree_path="$root_dir/.worktrees/$branch"
type_dir="${worktree_path%/*}"
git check-ref-format --branch "$branch" > /dev/null
git rev-parse --verify --end-of-options "$base_ref^{commit}" > /dev/null
if [[ -e "$type_dir/.git" ]]; then
  echo "Worktree type directory already contains a checkout: $type_dir" >&2
  exit 2
fi
if [[ -e $worktree_path || -L $worktree_path ]]; then
  echo "Worktree path already exists: $worktree_path" >&2
  exit 2
fi
if git show-ref --verify --quiet "refs/heads/$branch"; then
  echo "Branch already exists: $branch" >&2
  exit 2
fi

mkdir -p -- "$type_dir"
git worktree add --relative-paths -b "$branch" -- "$worktree_path" "$base_ref"
printf 'Worktree: %s\nBranch: %s\n' "$worktree_path" "$branch"
