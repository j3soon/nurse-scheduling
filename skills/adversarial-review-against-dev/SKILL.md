---
name: adversarial-review-against-dev
description: Review the current branch against origin/dev as a skeptical reviewer, verify each finding, fix the clear defects as new self-contained commits, and ask about findings that may be intended or need a design decision. Use for an adversarial or pre-PR review of a branch. Do not use for existing PR review comments (resolve-review-comments), failing CI (fix-github-ci), security scans (security-scan), or HTML review pages (html-commit-review).
---

<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- SPDX-FileCopyrightText: 2026 Johnson Sun -->
<!-- This file is mostly AI generated. -->

# Adversarial Branch Review

Review a branch before it reaches `dev`. Find commits and code that are wrong,
redundant, or risky. Fix the findings that are clearly worth fixing, and commit
each fix before you start the next one.

## Establish the review range

1. Run Git in the branch's checkout, which can be a linked worktree. If Git
   reports dubious ownership, set `safe.directory` for that path with
   `GIT_CONFIG_COUNT`, `GIT_CONFIG_KEY_0`, and `GIT_CONFIG_VALUE_0`. Export the
   same variables for tests, because some tests call Git.
2. Fetch `dev` as the repository `AGENTS.md` describes. Set the base to
   `git merge-base HEAD FETCH_HEAD`. The review range is `base..HEAD`.
3. Inspect the worktree and record unrelated changes. Fixes must not include
   them.
4. Read the instructions of every module that the range changes.
5. List the dev commits after the base that change the same files. If they
   change the same behavior, tell the user whether a merge of dev first would
   change the findings. Merge only when the user asks.

## Review the commits

List the commits in order with `git log --stat base..HEAD`. Flag these
problems:

- A later commit in the range reverts or replaces the commit. Its message now
  describes code that no longer exists.
- The commit mixes unrelated changes, or it is a fixup that belongs in an
  earlier commit.
- The message breaks the repository's commit rules or does not match the diff.
- A behavior change has no test, or a test has no matching behavior change.

Report history problems, but do not rewrite reviewed or published history
unless the user authorizes it. Fix the code with new commits instead.

## Review the net change

Read `git diff base...HEAD` one area at a time, then read the code around each
change. Check these properties:

- Correctness: failure order, cancellation, retries, timeouts, partial output,
  and races between a run and its persistence.
- Contracts: every producer and consumer of a changed event, field, or stored
  format. Include the backend projection, the frontend decoder and reducer, the
  saved browser state validators, exports, and PostgreSQL replay.
- Leftovers: flags that always have the same value, unused props or
  parameters, dead branches, and docs that describe removed behavior.
- Configuration: settings, environment examples, every Compose variant, README
  tables, and user docs must agree.
- Tests: tests that sleep for real backoff delays, tests that wait for
  background work without a condition, tests that pass without the fix, and
  tests that duplicate other tests.
- Evidence: prompt receipts, fixture hashes, and golden files whose inputs
  changed.
- Interaction with dev: semantic conflicts that a clean textual merge hides.

Before you call code wrong, use `git log -S` or `git blame` to find why it
exists. Some unusual behavior is intended.

## Verify and classify

Verify every finding before you report it. Reproduce it with a concrete input,
a focused failing test, or a code trace through all callers. Drop a finding
that you cannot support.

Classify each verified finding:

- Fix: a clear defect or leftover with one reasonable fix.
- Ask: a behavior, product, or policy choice, or a finding that can be
  intended. Give the options and recommend one.
- Skip: a style preference or noise. Give a one-line reason.

Rank the findings by impact. For each finding, give `path:line`, the failure
scenario, and the proposed fix.

If the user asked only for a review, stop and report. Otherwise fix the Fix
findings, and ask about all Ask findings in one question.

## Fix and commit along the way

Fix one finding, or one group of tightly coupled findings, at a time:

1. Write a focused test that fails for the reported reason, and record the
   failing assertion. For a defect that the browser shows, extend an E2E test.
   Run it once without the fix to confirm that it fails.
2. Implement the smallest complete fix, with its docs and configuration.
3. Run the affected checks from the module `AGENTS.md`. Pass
   `--base FETCH_HEAD` to include committed branch changes. For PostgreSQL
   suites, confirm that the database cases ran. If the finding was
   intermittent, run its test several times.
4. Commit the fix as a new commit before you start the next finding. Follow
   the repository commit rules and inspect the stored message.

For a stale prompt receipt, run the comparison again. Do not copy new
fingerprints into an old receipt. If the new comparison shows no benefit,
report the prompt step instead of refreshing its receipt.

When the user answers an Ask finding, implement the chosen option as its own
commit with the same steps.

## Finish

1. Run the combined affected validation for the whole range. Include the full
   E2E suite when `web-frontend/` changed. Run long checks in the background.
2. Run `git diff --check base..HEAD` and confirm that the worktree is clean.
3. Report these items:
   - each new commit and the finding that it fixes
   - the skipped findings and open questions, with reasons
   - the validation results, with correctness separate from performance
   - remaining risks, and suggested improvements to `AGENTS.md` or skills
4. When the environment cannot push, ask the user to push from the host.
