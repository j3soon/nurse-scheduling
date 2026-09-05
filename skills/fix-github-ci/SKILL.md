---
name: fix-github-ci
description: Diagnose and fix failing GitHub Actions jobs from logs or run links, especially platform-specific and flaky test failures. Use when asked to repair an existing GitHub CI failure. Do not use to design a new pipeline or investigate failures outside GitHub Actions.
---

# Fix GitHub CI

Treat the failing workflow or job as the observation point, not the presumed
source of the defect. Repair the root cause while preserving the behavior and
coverage the CI job is intended to enforce.

## Investigate

Inspect the failure log, runner matrix, workflow step, and exact command that
failed. Reproduce the smallest relevant command locally when possible, then
compare the local environment with the runner context.

Use the evidence to distinguish among an application defect, a non-portable or
flaky test, incorrect workflow setup, a dependency mismatch, and a transient
runner or external-service failure. Consult focused history when the intended
behavior is unclear.

## Repair

Make the smallest change in the layer that owns the cause.

- Fix application code when CI exposes incorrect product behavior.
- Make tests deterministic and platform-neutral when they rely on incidental
  timing, ordering, filesystem, shell, locale, or environment behavior.
- Change the workflow when its setup or configuration is the actual defect.
- Treat infrastructure failures as infrastructure failures rather than turning
  them into unrelated code changes.

Avoid platform skips, weakened assertions, arbitrary delays, and blanket retries
unless they are part of the intended contract. A CI fix should remove the faulty
assumption without reducing meaningful coverage.

## Validate

Run the original failing command first, then the affected checks and the exact CI
step when practical. If the runner platform cannot be exercised locally, state
that limitation clearly. Report the root cause, changed layer, validation
results, and any remaining runner-specific uncertainty.
