<!--
This file is part of Nurse Scheduling Project, see <https://github.com/j3soon/nurse-scheduling>.
Copyright (C) 2023-2026 Johnson Sun
SPDX-License-Identifier: AGPL-3.0-or-later
-->
<!-- This file is mostly AI generated. -->

# System prompt evidence

The [ordered manifest](../../nurse_scheduling/ai/prompts/system-steps.json) maps each production clause to its
behavioral hypothesis, witness testcase, and contrasting controls. It keeps one reviewed aggregate receipt per
clause: model, paired pass counts, infrastructure-error count, and an input fingerprint. Counts are directional
evidence for the named model and cases, not proof that a clause is universally necessary.

## Repository and artifact boundary

Keep prompt text, testcase definitions, hypotheses, concise scope notes, and the latest aggregate receipts tracked.
Keep exact prompt snapshots, reference and environment hashes, timing, tokens, trajectories, diagnostic failures,
old receipts, and round-by-round analysis under ignored repository-root `artifacts/`. Commit messages should name
the motivating testcase and briefly state the behavior change. Do not grow this page into a run journal.

CI checks that every shipped clause has a clean benefit witness. The receipt's `input_sha256` binds its clause,
parsed testcase, and fixture. Editing any of these invalidates the receipt. Controls have their own paired counts,
so a targeted deeper investigation can extend one witness without rerunning already verified controls.
CI validates reviewed receipts locally. It does not call the provider or require ignored artifacts to exist.
Receipts describe their tested context, not a fresh evaluation of every later prompt composition.

## Reproduce a comparison

From the repository root with credentials in ignored `docker/.env` or `docker/.env.staging`:

```bash
./scripts/run_ai_eval.sh --prompt-compare-step N --repeat 3 --jobs 4
./scripts/run_ai_eval.sh --prompt-compare-step N --case CASE_ID --repeat 10 --jobs 4
```

Use three repeats routinely. Up to ten are available for an explicitly requested deeper investigation. Compare only
that clause's cases by default. Use full-prompt ablation when requested or when investigating an interaction.
Exact historical contexts are preserved in the ignored reports.

Inspect the raw trajectories before replacing a receipt. Require all after attempts to pass, no infrastructure
errors, and either a correctness gain or a predeclared relative cost gain with both arms passing. Retain behavioral
failures. Infrastructure-invalid pairs may be rerun only with the original failures preserved in artifacts.

For a stronger witness, freeze the case and grading before comparing, then confirm a promising gain in an
independent batch with unchanged inputs. Difficulty alone is not evidence. Keep passing ties as controls,
and do not require a guide read as a substitute for correct app behavior. Correct grader mistakes in both
arms, preserve the original results, and rerun the affected comparison.

Keep behavioral regression cases when removing redundant guidance. They need not remain in the active
clause-evidence manifest. Identify clauses by their stable IDs when reviewing results, since removing a
section changes the numeric step selectors used by historical commands.

The literal-expression witness measures avoiding validation repairs, not eventual YAML correctness. The startup
witness holds optimizer-error guidance fixed in both arms. Optimizer cases use a controlled tool and do not validate
real solver output or completion callbacks. Those durable limits remain beside their receipts in the manifest.
