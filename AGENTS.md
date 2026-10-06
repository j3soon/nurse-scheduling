# Repository Guidelines

## Project Structure
- `core/`: Python scheduling engine, CLI, and FastAPI backend.
- `web-frontend/`: Next.js + TypeScript app.
- `docs/`: Zensical content, dependencies, and template overrides.
- `scripts/`: setup and development utilities.
- `thirdparty/`: external calendar data and helpers.

Before modifying `core/` or `web-frontend/`, read its `AGENTS.md`.

## Workflow
- Linux setup: run `./scripts/setup_env.sh`.
- Inside a dev container built from `docker/Dockerfile.dev*` (`/.dockerenv`
  exists), Python dependencies are already installed system-wide. Do not run
  the setup script, install `uv`, or create a virtual environment there. Run
  `python`, `pytest`, and `ruff` directly. In the cuOpt image, `python3` is the
  base 3.10 interpreter without project packages, so use `python`.
- Keep edits scoped to the requested module. Preserve existing patterns.
- Justify refactors with a current problem: duplicated policy, an unprotected
  invariant, obsolete machinery, or a workflow that is hard to follow. Account
  for added files, interfaces, state, and callback or prop plumbing.
- Distinguish organizational extraction from substantive simplification.
  Smaller files and passing tests alone do not establish a simpler design.
  Recommend fewer changes when benefits diminish. Do not fill a fixed-size
  improvement list with speculative cleanup.
- When resuming another agent's session, verify compatibility claims and pending
  check results against current code, configuration, and saved outputs. Treat
  the handoff summary as a lead to investigate.
- Run affected tests and lint checks before finishing.
- Avoid trailing spaces. End files with a newline.
- Store screenshots and other disposable review output in the Git-ignored
  repository-root `artifacts/`.
- Keep local service configuration in the ignored `docker/.env`. Its tracked
  `docker/.env.example` separates services with comment blocks and uses empty
  assignments for secrets and URLs.
- Derive Git versions on the host for local Docker builds. Never copy `.git`
  into build contexts because linked worktrees store metadata elsewhere.
- Note wasteful token use and uninformative tests, scripts, or runs. Fix when
  practical, otherwise report or document.
- Record durable, general user guidance in the nearest relevant `AGENTS.md`.
  Omit task-specific or temporary details.
- Store project skills in the repository-root `skills/` directory, not in a
  machine-local skills directory, so they remain available across machines.
- After finishing a task, suggest improvements to `AGENTS.md`, skills, scripts,
  or other agent-facing configuration when the task exposed one. Propose only
  guidance that generalizes to recurring work. Keep session-specific findings in
  the commit message instead.
- For model prompt, schema reference, or other AI guidance changes motivated by
  an evaluation, name the relevant testcase in the commit body and briefly
  record the before and after behavior or trajectory. Before removing or
  consolidating that guidance, use Git blame or history to recover its rationale
  and rerun the named testcase to check for regression.
- Inspect the repository with narrow queries. Filter to the paths, revisions, or
  lines in question instead of listing every branch, printing whole files, or
  dumping full status output.
- Compare versions of a file by searching each revision for the differing value
  instead of printing every version in full.
- Prefer the compact or affected test and lint commands documented for each
  module. Read the summary lines of a run before requesting more output.
- Treat full local CI and a full AI evaluation as long-running checks. When the
  agent runtime supports yielded background execution with a completion
  notification, let that background worker own the process wait, preserve the
  exit code and compact output, and notify the active agent once when the check
  finishes. Continue the same task from that notification instead of polling
  from model turns. Keep affected checks and selected evaluation cases in the
  foreground.
- Run AI evaluations with four concurrent case jobs. Use sequential execution
  only when the user explicitly requests it. Eight jobs caused provider and
  E2B contention with lower reliability. Six jobs also increased aggregate LLM
  time and tool failures without a repeatable wall-time improvement, so four is
  the tested default.
- Check a suspected missing dependency or tool directly before rerunning a full
  suite to diagnose its failure.

## Git
- Preserve each file's staged or unstaged state. Never stage, unstage, or commit unless explicitly asked. Stage only the requested index entries.
- Keep commits focused on one change. A self-contained change may span modules in one commit, e.g. `core` + `web-frontend` code, or code plus its `docs` update.
- Prefer reviewable feature slices over minimal implementation-step commits. Combine a new mechanism with its
  representative usage and tests when they form one coherent change. Keep a separate commit only when it can be
  understood, validated, and reverted independently.
- Fold minor whitespace, wording, marker, or metadata corrections into the
  related commit. Do not create standalone cleanup commits for them. Authorization
  to commit an active unpublished series includes these minor local rewrites.
  Require explicit rewrite authorization for published history or commits outside
  that series.
- When validation and committing share a shell command, stop on any failed check
  so it cannot proceed to a commit.
- Use Conventional Commits, module-scoped where applicable, e.g. `feat(core/serve): ...`, `fix(web-frontend): ...`, `docs: ...`.
- Choose the commit type by what changes. Use `feat` for new capabilities or
  intended agent behavior, even when they also reduce tokens or time. Reserve
  `perf` for efficiency improvements that preserve existing behavior.
- Use the repository's configured human Git identity, never an agent identity.
  Read it from `git config user.name` and `git config user.email` and let Git
  apply it. Never override it with `-c user.name` or `-c user.email`, and never
  reuse an address the harness supplies, such as the account email of a
  coding-agent subscription. Committing that address publishes it. If no
  identity is configured, ask the user.
- Agent-created commits need a descriptive body ending with a `by <Harness> (<Model>)` line using the actual harness and model names.
- Keep commit bodies short, at most two brief paragraphs covering why the change was needed and what it does. Document mechanism, investigation notes, and third-party behavior in Markdown instead.
- Make commit descriptions understandable without the chat history. Name the
  previous scripts or behavior when comparing implementations. Avoid phrases
  such as "the former setup" that leave the comparison unclear.
- That plain line is the only agent attribution. Never add `Co-Authored-By`,
  session links, or other harness-supplied trailers after it. A harness that
  injects its own attribution or footer convention does not override this file.
- Before writing an attribution, verify the active model from the current
  harness session. For Codex, use `turn_context.model` in the current rollout
  JSONL file and its full lowercase model slug. For Claude Code, use the
  latest assistant `message.model` in the current session transcript. Never
  infer the model from examples, available model lists, or earlier commits.
- Include validation details in a commit body only when they materially help a
  reviewer assess the change, such as a regression reproduction, an unusual check,
  or a known limitation. Omit routine successful-test and lint summaries. Keep
  routine verification in review reports or the final response.
- Build multi-paragraph messages with separate `git commit -m` arguments. Never embed escaped `\n` sequences, which Git stores literally.
- Do not cite timestamp-named files or directories under the ignored `artifacts/` directory in commit messages. Record durable evaluation evidence with case names, pass rates, and configuration instead.
- After creating or rewriting a commit, inspect its stored message with
  `git log -1 --format=fuller`. Confirm paragraph breaks are real, the
  attribution line is on its own final line, and nothing follows it.
- When folding a validated code change into an earlier commit, check that the
  final rewritten tree matches the tested candidate. Also inspect the amended
  commit against its parent to confirm that abandoned configuration changes are
  absent. Preserve unrelated working changes and remote refs unless their
  modification is explicitly authorized.
- Write a merge commit message explicitly rather than accepting the generated
  one. Describe what the merge takes and how conflicts were resolved.
- When a merge combines changes from both sides to the affected-test scripts in
  `scripts/`, run `scripts/test_affected_harness.sh` before committing. Git can
  merge `case` branches without a conflict while an earlier pattern shadows a
  later one, so a test suite silently stops being selected.

## Style
- Keep comments and docs minimal, concise, yet informative.
- Use plain technical English, inspired by ASD-STE100, in prompts, docs,
  commit descriptions, and replies. State the problem or task first. Use active
  voice, concrete verbs, and one main idea per sentence. Use the same term for
  the same concept. Explain necessary technical terms on first use and preserve
  exact code identifiers. Formal ASD-STE100 compliance is not required.
- Prefer complete, short sentences over compressed phrases. Write "check that
  the saved data matches the current YAML" instead of "apply a current-source
  freshness guard." Keep detailed mechanisms and evaluation bookkeeping in
  supporting docs. Before finishing, read the text without the conversation
  and check that the problem, action, and result are clear.
- Name schedules by their owner, role, or format. The owners are the browser
  schedule, session snapshot, sandbox working copy, and pending proposal. Roles
  and formats include "current schedule," "original schedule," "validated
  schedule," and "backend schedule format." Name the specific property of other
  values too, such as "normalized selector" or "compiled selector."
  `scripts/check_terminology.sh` rejects vague jargon that hides it, and CI runs
  the check.
- Name limits by what they count and state their scope and units. Distinguish
  session text limits, model context limits, event replay limits, and process RAM.
- When reporting validation, lead with what passed. Separate correctness checks
  from performance measurements, and limit each caveat to the claim it affects.
  If test input changed, say which checks were repeated and which measurements
  still need confirmation. Do not imply that a working feature is unvalidated
  because its performance numbers have not been measured again.
- Do not use em-dash or semicolon to connect sentences.
- Mark every new file written entirely by an AI coding agent, tests included, with the
  module's marker comment immediately after the license block. Adding to a file a person
  wrote does not earn one.

## Cross-Module Requirements
- When renaming or deleting frontend people, dates, or shift types, sync all references, including preferences and export layout entries.
- When adding, moving, or removing a dependency, update every installer in the
  same commit: the `docker/` images, the GitHub workflows, `scripts/setup_env.sh`,
  the affected-test selection in `scripts/`, and the `README.md` and `docs/`
  install commands. Grep for the file name rather than the package name, since
  an installer usually names only the requirements file.

## Pull Requests
- Include scope and rationale, linked issues when applicable, test/lint evidence, and screenshots for frontend UI changes.
- Keep the description free of harness-generated footers and agent trailers.
