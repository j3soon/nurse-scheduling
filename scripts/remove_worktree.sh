#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Johnson Sun
# This file is mostly AI generated.

set -euo pipefail

usage() {
  echo 'Usage: scripts/remove_worktree.sh TYPE/NAME [--base REF] [--update-env-staging | --keep-env-staging]'
  echo 'Remove .worktrees/TYPE/NAME after checking that REF (default: dev) contains every branch commit.'
  echo 'Exit 3 without removing anything when the checkout changed docker/.env.staging.'
  echo 'Then rerun with --update-env-staging to copy that file to the main clone,'
  echo 'or with --keep-env-staging to leave the main copy unchanged.'
}

branch=''
base_ref=dev
env_choice=''
while (($#)); do
  case $1 in
    --help)
      usage
      exit 0
      ;;
    --base)
      (($# >= 2)) || { usage >&2; exit 2; }
      base_ref=$2
      shift 2
      ;;
    --update-env-staging | --keep-env-staging)
      choice=${1#--}
      choice=${choice%-env-staging}
      if [[ -n $env_choice && $env_choice != "$choice" ]]; then
        echo 'Pass only one of --update-env-staging and --keep-env-staging.' >&2
        exit 2
      fi
      env_choice=$choice
      shift
      ;;
    -*)
      usage >&2
      exit 2
      ;;
    *)
      [[ -z $branch ]] || { usage >&2; exit 2; }
      branch=$1
      shift
      ;;
  esac
done
if [[ ! $branch =~ ^[a-z][a-z0-9-]*/[A-Za-z0-9][A-Za-z0-9._-]*$ ]]; then
  usage >&2
  exit 2
fi

root_dir="$(git rev-parse --show-toplevel)"
if [[ ! -d "$root_dir/.git" ]]; then
  echo 'Run from the main clone, which owns .worktrees and the shared docker/.env.staging.' >&2
  exit 2
fi
worktree_path="$root_dir/.worktrees/$branch"
if [[ ! -e "$worktree_path/.git" ]] ||
  [[ "$(git -C "$worktree_path" rev-parse --show-toplevel 2> /dev/null)" != "$worktree_path" ]]; then
  echo "No checkout found at $worktree_path" >&2
  exit 2
fi
current="$(git -C "$worktree_path" branch --show-current)"
if [[ $current != "$branch" ]]; then
  echo "The checkout is on '${current:-detached HEAD}', not $branch." >&2
  exit 2
fi
if ! git rev-parse --verify --quiet --end-of-options "$base_ref^{commit}" > /dev/null; then
  echo "Unknown base ref: $base_ref" >&2
  exit 2
fi

unmerged="$(git log --oneline "$base_ref..$branch" --)"
if [[ -n $unmerged ]]; then
  printf '%s does not contain these %s commits:\n%s\n' "$base_ref" "$branch" "$unmerged" >&2
  echo 'Integrate them first. Pass --base FETCH_HEAD after fetching dev when the local dev is behind.' >&2
  exit 1
fi
if [[ -n "$(git -C "$worktree_path" status --porcelain)" ]]; then
  echo "The checkout has uncommitted or untracked changes: $worktree_path" >&2
  exit 1
fi

hash_file() {
  if [[ -f $1 ]]; then
    git hash-object --no-filters -- "$1"
  fi
}

# Print the names of settings that differ between two env files. Never print values.
changed_keys() {
  awk '
    match($0, /^[[:space:]]*(export[[:space:]]+)?[A-Za-z_][A-Za-z0-9_]*=/) {
      key = substr($0, 1, RLENGTH - 1)
      sub(/^[[:space:]]*(export[[:space:]]+)?/, "", key)
      value = substr($0, RLENGTH + 1)
      if (FILENAME == ARGV[1]) old[key] = value
      else new[key] = value
    }
    END {
      for (key in new) if (!(key in old)) print "  added: " key
      for (key in old) if (!(key in new)) print "  removed: " key
      for (key in new) if ((key in old) && old[key] != new[key]) print "  changed: " key
    }' "$1" "$2" | sort
}

env_file=docker/.env.staging
worktree_env="$worktree_path/$env_file"
main_env="$root_dir/$env_file"
worktree_hash="$(hash_file "$worktree_env")"
main_hash="$(hash_file "$main_env")"
# add_worktree.sh records the copied version in the checkout's Git directory.
record="$(git -C "$worktree_path" rev-parse --absolute-git-dir)/env-staging.copied"
copied_hash="$(cat -- "$record" 2> /dev/null || true)"

if [[ -z $worktree_hash || $worktree_hash == "$main_hash" ]]; then
  :
elif [[ $worktree_hash == "$copied_hash" ]]; then
  echo "Only the main clone changed $env_file after the copy. Keeping the main copy."
elif [[ $env_choice == update ]]; then
  if [[ -f $main_env ]]; then
    # Keep the main file's mode and owner.
    cat -- "$worktree_env" > "$main_env"
  else
    mkdir -p -- "${main_env%/*}"
    cp -p -- "$worktree_env" "$main_env"
  fi
  echo "Updated the main clone's $env_file from the checkout."
elif [[ $env_choice == keep ]]; then
  echo "Kept the main clone's $env_file. The checkout's copy is removed with it."
else
  {
    echo "The checkout changed $env_file. Settings that differ from the main clone:"
    main_source=/dev/null
    [[ -z $main_hash ]] || main_source=$main_env
    keys="$(changed_keys "$main_source" "$worktree_env")"
    echo "${keys:-  only comments or formatting differ}"
    if [[ -n $copied_hash && $main_hash != "$copied_hash" ]]; then
      echo 'The main copy also changed after the checkout was created. Updating it replaces those changes.'
    fi
    echo 'Rerun with --update-env-staging to copy the checkout file to the main clone,'
    echo 'or with --keep-env-staging to leave the main copy unchanged.'
  } >&2
  exit 3
fi

git worktree remove -- "$worktree_path"
rmdir -- "${worktree_path%/*}" 2> /dev/null || true
printf 'Removed: %s\nDelete the branch when it is no longer needed: git branch -d %s\n' "$worktree_path" "$branch"
