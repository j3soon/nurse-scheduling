#!/usr/bin/env bash

affected_base=HEAD
affected_full=false
affected_list=false
affected_paths=()

affected_parse_args() {
  local root_dir="$1"
  local base_ref=HEAD
  shift

  while (($# > 0)); do
    case "$1" in
      --base)
        if (($# < 2)) || [[ -z "$2" ]]; then
          echo "--base requires a Git ref." >&2
          return 2
        fi
        base_ref="$2"
        shift 2
        ;;
      --full)
        affected_full=true
        shift
        ;;
      --list)
        affected_list=true
        shift
        ;;
      --)
        shift
        affected_paths+=("$@")
        break
        ;;
      -*)
        printf 'Unknown option: %s\n' "$1" >&2
        return 2
        ;;
      *)
        affected_paths+=("$1")
        shift
        ;;
    esac
  done

  if [[ "$affected_full" == true ]] && ((${#affected_paths[@]} > 0)); then
    echo "--full cannot be combined with explicit paths." >&2
    return 2
  fi
  if [[ "$base_ref" != HEAD ]] && ((${#affected_paths[@]} > 0)); then
    echo "--base cannot be combined with explicit paths." >&2
    return 2
  fi
  if [[ "$base_ref" != HEAD ]]; then
    if ! git -C "$root_dir" rev-parse --verify --quiet "$base_ref^{commit}" > /dev/null; then
      printf 'Unknown Git base: %s\n' "$base_ref" >&2
      return 2
    fi
    if ! affected_base="$(git -C "$root_dir" merge-base HEAD "$base_ref")"; then
      printf 'No merge base with: %s\n' "$base_ref" >&2
      return 2
    fi
  fi
}

affected_changed_files() {
  local root_dir="$1"
  local pathspec="$2"
  {
    git -C "$root_dir" diff --no-renames --name-only --diff-filter=ACDMRTUXB -z "$affected_base" -- "$pathspec"
    git -C "$root_dir" ls-files --others --exclude-standard -z -- "$pathspec"
  } | LC_ALL=C sort -zu
}
