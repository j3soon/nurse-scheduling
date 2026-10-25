---
name: fix-github-ci
description: Diagnose and fix failing GitHub Actions jobs from logs or run links, especially platform-specific and flaky test failures. Use when asked to repair an existing GitHub CI failure. Do not use to design a new pipeline or investigate failures outside GitHub Actions.
---

# Fix GitHub CI

Treat the failing workflow or job as the observation point, not the presumed
source of the defect. Repair the root cause while preserving the behavior and
coverage the CI job is intended to enforce.

## Investigate

Check `test -f /.dockerenv` and follow the root
`AGENTS.md` environment rules. Setup commands, interpreters, and absolute
paths differ between a dev container (`/workspace`) and a host checkout.

Prefer authenticated `gh` for GitHub reads. It uses an existing `GH_TOKEN`
automatically. Check `gh auth status >/dev/null 2>&1` and report only whether
authentication succeeded. Do not print credentials. If the CLI is unavailable
or lacks access, try a connected GitHub integration. Do not assume an
integration has the same access as the CLI.

Identify the relevant commit, workflow run, attempt, failed job, and failed
step before downloading logs. Use `--json` with `--jq` to print only these
fields. For a supplied run, a compact job summary is:

```sh
gh run view RUN_ID --repo OWNER/REPO --json headSha,attempt,jobs \
  --jq '{sha: .headSha, attempt, failed_jobs: [.jobs[] | select(.conclusion == "failure") | {id: .databaseId, name, steps: [.steps[] | select(.conclusion == "failure") | {name, number}]}]}'
```

For a PR, select runs for its current head SHA. If those runs pass, report
that state instead of investigating an unrelated older failure. Keep older
failures separate when the user explicitly asks about them. Paginate run and
job listings when the relevant entry is not on the first page.

From the repository root, save the selected job's failed-step logs:

```sh
mkdir -p artifacts
gh run view RUN_ID --repo OWNER/REPO --attempt ATTEMPT --job JOB_ID \
  --log-failed > artifacts/ci-RUN_ID-JOB_ID-ATTEMPT.log
```

Keep the run, job, and attempt in cache filenames. Reuse cached logs for
completed attempts. Search the saved log with `rg -n` and read small line
ranges around the failure. Do not print the whole log. Use `--log` for the
selected job only when failed-step output omits necessary setup or surrounding
diagnostics.
When CLI step names show `UNKNOWN STEP`, use job metadata to identify the step.

If log access fails, report the specific authentication, permission, retention,
or availability error. Public unauthenticated REST can provide run and job
summaries, but cannot download Actions logs. Try authenticated integration
access before falling back to local reproduction or requesting `GH_TOKEN`
through the container environment, as the root `AGENTS.md` describes.

Inspect the failure log, runner matrix, workflow step, and exact command that
failed. Reproduce the smallest relevant command locally when possible, then
compare the local environment with the runner context.

Use the evidence to distinguish among an application defect, a non-portable or
flaky test, incorrect workflow setup, a dependency mismatch, and a transient
runner or external-service failure. Consult focused history when the intended
behavior is unclear.

For Windows-only hash failures or missing source-derived data, compare the
hashed text with the bytes on disk. Check both Git checkout line endings and
text-write newline translation. `Path.read_text(encoding="utf-8")` normalizes
CRLF to LF, while `Path.write_text()` can write CRLF on Windows. A hash of the
normalized text can therefore differ from a hash of the file bytes.

When Playwright reports only that `config.webServer` could not start, inspect
its command and run the build step directly with the same environment. Save
stdout and stderr under the repository-root `artifacts/` directory. Compact
output such as `--quiet` can hide build and TypeScript diagnostics. Diagnose
those diagnostics before rerunning the browser suite.

For timing failures, check clock resolution in the runner's Python version.
Sequential calls to a monotonic clock can return the same value. Reproduce ties
with a frozen clock. Replace only the tested module's clock when an async test
must keep the event loop's timers running.
An asyncio timer can expire before a coarse monotonic clock reaches its deadline.
Check the timeout context's `expired()` state before treating its error as a
retryable request timeout.
Test elapsed-time accounting with a controlled performance clock and scripted
work. Do not use an asyncio sleep as a portable lower bound for measured time.

On Windows, `shutil.which("bash")` can find a WSL launcher without an installed
distribution. Prefer Git for Windows' `bin/bash.exe` wrapper and check that the
interpreter runs before using it. Keep shell help checks portable by reading
UTF-8 text with normalized line endings and sending encoded bytes to Bash stdin.
Text-mode subprocess input can translate LF back to CRLF on Windows.

## Repair

Make the smallest change in the layer that owns the cause.

- Fix application code when CI exposes incorrect product behavior.
- Make tests deterministic and platform-neutral when they rely on incidental
  timing, ordering, filesystem, shell, locale, or environment behavior.
- Change the workflow when its setup or configuration is the actual defect.
- Treat infrastructure failures as infrastructure failures rather than turning
  them into unrelated code changes.

Choose whether each hash identifies normalized text or exact bytes. For text
evidence, normalize line endings consistently when creating and checking its
hash. Trace its creation and validation, including test metadata that supplies
the hash. For fixtures bound to exact bytes, write `text.encode("utf-8")` with
`Path.write_bytes()`. Preserve source checks whose contract requires exact bytes.

Avoid platform skips, weakened assertions, arbitrary delays, and blanket retries
unless they are part of the intended contract. A CI fix should remove the faulty
assumption without reducing meaningful coverage.

## Validate

Run the original failing command first, then the affected checks and the exact CI
step when practical. If the runner platform cannot be exercised locally, state
that limitation clearly. Report the root cause, changed layer, validation
results, and any remaining runner-specific uncertainty.

For newline-related fixes, cover LF and CRLF and check that a real content
change still fails the hash check. If Windows is unavailable, simulate checkout
line endings and default text-write translation separately. Run the affected
suites under the simulation to cover other code and fixtures that create or
validate the same hash.
