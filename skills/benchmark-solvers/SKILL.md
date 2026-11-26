---
name: benchmark-solvers
description: Compare solver versions, model formulations, or settings from small cases through representative real Schedule Specs. Use for paired cuOpt and OR-Tools CP-SAT benchmarks, score and runtime comparisons, and solver upgrade performance checks.
---

<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- SPDX-FileCopyrightText: 2026 Johnson Sun -->
<!-- This file is mostly AI generated. -->

# Benchmark Solvers

Use the [real-case fixtures and benchmark documentation](../../core/tests/real/README.md).
For the 87-person ward, the existing score target is `4_470_000_000_000`.
Use the real-case wrapper when counting critical request notes. It adds export
formatting without changing the optimization problem.

## Increase the case size in stages

1. Start with a small Schedule Spec that exercises the changed constraint.
   Check feasibility and exact scores on fixed assignments, including boundary
   cases. Use short paired solves to check the predicted change in model size
   or search behavior. Resolve correctness failures before proceeding.
2. Use a larger synthetic or existing case that repeats the same constraint
   enough to put pressure on presolve and search. Keep the preference mix
   comparable when scaling a synthetic case. Compare presolved model size,
   time to the same score or optimum, and the quality reached at a fixed budget.
   Record mixed results as well as gains.
3. Finish with a representative real Schedule Spec through the production
   solver entry point. Allow enough time for the baseline to reach the usual
   quality target. Repeat matched runs and replay assignments from both
   formulations. Base the performance conclusion for each solver on its own
   real-case results.

Record the input, budget, and result for each stage so a later run can
distinguish a correctness check from a performance comparison.

## Set up the comparison

- Compare the parent and candidate revisions for a formulation change. Use the
  same revision for a solver-only change. For cuOpt, reuse the same MPS across
  solver versions when only the solver changes.
- Use isolated checkouts and runtimes as needed. Record revision and input hash,
  solver version, CPU and GPU, thread settings, seed, and solver time limit.
  Run one measured solve at a time on an otherwise idle machine. Match the
  conditions across both sides and record deliberate differences.
- For a quick repeated comparison, use five pairs with seeds 1 through 5.
  Alternate which side runs first within each pair to reduce run-order effects.
  Use the same limit on both sides. The 87-person ward comparison used 120
  seconds. Choose a limit that gives each solver a chance to reach the quality
  target. Matching seeds do not make parallel solver runs deterministic.

## Run and verify

- For native CP-SAT, use the application entry point and the
  [real-case progress wrapper](../../core/tests/real/run_schedule.py).
  For explicit seed pairs, set `solver.parameters.random_seed` on the
  underlying `CpSolver` before solving. The application's deterministic mode
  also changes the worker count. Record the solver wall time.
- For cuOpt formulation comparisons, capture the PuLP model at
  `BasePuLPSolver.solve` after the scheduler sets the objective. Export it with
  `model.writeMPS(path, mpsSense=pulp.LpMinimize)` and preserve variable names.
  Check the objective constant if comparing MPS scores directly. The minimization
  export reverses the application's maximization sign. Use the application
  entry point to measure PuLP integration behavior.
- With cuOpt 26.8, verify that `cuopt_cli --version` and `nvidia-smi` work.
  If the root LP fails with `cudssSetThreadingLayer` status 3, use `ldd` on
  the cuDSS threading library to check whether it can find `libgomp.so.1`.
  On Ubuntu, `libgomp1` supplies that library. See [NVIDIA's image fix](https://github.com/NVIDIA/cuopt/pull/1888).
- Save a log and solution for each cuOpt run. For example, with the model and
  output paths set by the caller:

  ```bash
  timeout -k 15 150 cuopt_cli "$model" --time-limit 120 --random-seed "$seed" \
    --solution-file "$solution" > "$log" 2>&1
  ```

- Keep logs, status, model exports, and per-run measurements under the ignored
  repository-root `artifacts/` directory. Give the outer watchdog time for
  startup and solver shutdown. Record crashes, watchdog expirations, and any
  retries separately from completed solves.
- If the PuLP/cuOpt path crashes, try the exported model with `cuopt_cli`
  as a separate diagnostic. The MPS reader, objective sense, and variable
  ordering can differ from the application path. Report CLI measurements
  separately from application measurements.
- Validate schedules independently of logged objective values. For the ward
  cuOpt experiment, read all `shift_d{day}_s{shift}_p{person}` assignments
  from the solution file, check their integrality, and pass them as
  `forced_solution` to `schedule` with the original Schedule Spec and
  `ortools/cp-sat`. Require a feasible replay for the complete assignment.
  Use that replay's exact score and the real-case wrapper's critical note rules.

## Report

- Compare deterministic model counts before presolve, including variables,
  constraints, and matrix nonzeros where applicable. For a bounds change,
  also report how many domains tightened and by how much.
- Report final scores and elapsed solver seconds as mean ± sample standard
  deviation. Include counts reaching the quality target or gap tolerance,
  time to the target where available, and counts clearing critical requests.
  A run that reaches its limit without hitting a target has no observed
  time to target. Keep its final score in the fixed-budget comparison.
- Evaluate runtime and quality together. When both sides hit the time limit,
  the score is the useful comparison. When some runs finish early, state
  their termination condition and report solver runtime separately from
  end-to-end time. Treat small or inconsistent differences across seeds as
  inconclusive and report correctness separately.

## Lessons from the 87-person ward

The original cuOpt 26.8.0 run solved the root LP in 5.45 seconds and found a
bound close to CP-SAT's best score. Its incumbent still had 89 critical
request notes and 22 preferred staffing shortfalls at the 600-second limit.
When diagnosing a plateau, distinguish that case from a slow root LP or a
missing progress event. In cuOpt logs, the root LP objective is a bound and
`S` rows report incumbents from subproblems.

- **Equality at an upper bound.** For integer `x` in `[m, M]` with `m < M`,
  `z = [x == M]` requires only `x <= M - 1 + z` and
  `x >= m + (M - m) * z`. Each inactive implication reduces to an existing
  domain bound. This tight Big-M formulation removes the binary that would
  choose which side of an interior target a mismatch falls on. On the ward,
  it removed 15,251 variables, 30,502 rows, and 268,619 matrix nonzeros.
  cuOpt reached a higher mean score at the same 120-second limit. The smaller
  formulation reduced the auxiliary decisions the solver had to handle.
- **Preferred staffing shortfall.** With required staffing 12 and preferred
  staffing 13, actual staffing is 12 or 13 and the shortfall is 0 or 1.
  Giving the solver that bound directly tightened 90 domains from upper
  bounds of 13 or 14 to 1, with identical model counts. Across five pairs,
  cuOpt went from reaching its gap tolerance in three runs to reaching it in
  all five. Solver time fell from 116.63 ± 4.71 to 95.66 ± 7.91 seconds.
  The CP-SAT difference was inconclusive. These results show that bounds on
  auxiliary variables can affect incumbent quality. They do not isolate
  which cuOpt heuristic benefited.
- **Check presolve before drawing conclusions from model counts.** Replacing
  10,291 binary fixing rows with variable bounds produced the same presolved
  model dimensions and root bound as the baseline. Timing varied by seed.
  Sharing constraints across mutually exclusive transitions reduced matrix
  nonzeros from 470,776 to 430,408. In two screening runs it saved about 12
  seconds to solver exit, with similar time to the score target.
- **Test objective scaling on the current formulation.** Uniform rescaling
  preserves the ordering of schedules in exact arithmetic. It changes
  numerical tolerances in score units and can change solver search. Dividing
  all coefficients by one million helped in a screening run on the original
  MILP. With both formulation changes in place, the same trial reached the
  score target later and used its full 90-second budget.

### Search settings on the same MILP

For cuOpt 26.8.0, rerun the ward command above with a 90-second limit and
seeds 3 through 7. Compare the default with each flag separately. Use the
formulation with both changes above, which exports 59,041 variables and
69,850 constraints. The benchmark used an RTX PRO 6000 Blackwell Max-Q and a
Threadripper PRO 9965WX. Times are mean ± sample standard deviation in seconds.

| CLI setting | Time to 4.470 trillion | Solver time | Reached relative gap tolerance |
| --- | ---: | ---: | ---: |
| Default | 70.3 ± 11.8 | 86.3 ± 8.8 | 3/5 |
| `--mip-strong-branching-simplex-iteration-limit 1` | 61.8 ± 5.9 | 71.5 ± 10.7 | 5/5 |
| `--mip-cut-passes 1` | 65.2 ± 17.0 | 77.6 ± 10.6 | 4/5 |

All 15 runs used the same MILP, objective, and relative gap tolerance
(`1e-4`). Replayed scores were comparable and every schedule cleared the
critical requests. cuOpt 26.8.0 defaults to 200 simplex iterations per
trial branch. The one-iteration limit reduced mean strong-branching time
from 20.1 to 8.2 seconds. In a separate PuLP application run, solver time
fell from 79.9 to 64.0 seconds. One cut pass reduced mean cut-generation
time from 14.5 to 1.6 seconds, with more variable time to the score target.
Disabling cuts entirely
or limiting cuOpt to 12 CPU threads hurt schedule quality in screening.
Use these settings as experiment candidates. The evidence covers one real
Schedule Spec, and the one-iteration limit was slower on one seed.

### Shared shift-group matches in CP-SAT

For each person, date, and group, define a Boolean equal to the sum of the
assignment variables for that group. The daily assignment constraint makes
the sum either 0 or 1, including groups that contain OFF. Reuse this Boolean
when the same group appears in more than one soft succession. Encode each
succession as a native Boolean AND. This preserves the match and its score
for every schedule.

The staged recheck used three matched seeds per case on a Threadripper PRO
9965WX and RTX PRO 6000 Blackwell Max-Q. Fixed-assignment checks covered all
16 assignments in a two-day case with overlapping shift groups, OFF, and
history. CP-SAT and PuLP/CBC preserved every tested score. The two larger
synthetic cases used three two-shift groups, staffing and shift count
preferences, soft successions, and shift requests. Both CP-SAT formulations
reached the same verified optimum at each synthetic size.

| Synthetic case | Solver | Time limit | Baseline seconds | Shared-match seconds |
| --- | --- | ---: | ---: | ---: |
| 18 people, 10 days | CP-SAT | 7 s | 0.872 ± 0.270 | 0.225 ± 0.009 |
| 18 people, 10 days | cuOpt 26.8.0 | 7 s | 1.055 ± 0.036 | 1.443 ± 0.353 |
| 36 people, 18 days | CP-SAT | 20 s | 17.540 ± 2.036 | 2.054 ± 0.248 |

Times are mean ± sample standard deviation. PuLP/cuOpt 26.8.0 crashed during
root processing for all three seeds on the 36-person case in both
formulations. The exported models solved through `cuopt_cli` in 4.63 and
4.33 seconds in one diagnostic pair, with both schedules replaying at the
same optimum of 2,461. These CLI runs measure a different solve path.

On the 87-person ward, each application solve had a 120-second limit.
All returned schedules replayed with the same exact score in both
formulations. Time to the score target uses progress events for runs
whose final replay reached the target. CP-SAT seed 1 hit the outer watchdog
twice on the baseline. The paired CP-SAT results use seeds 2 through 4.
The cuOpt results use seeds 1 through 3.

| Ward metric | Baseline | Shared matches |
| --- | ---: | ---: |
| CP-SAT 9.15.6755 presolved variables | 48,431 | 41,444 |
| CP-SAT reached 4.470 trillion | 2/3 | 3/3 |
| CP-SAT time to target among hits (s) | 63.94 ± 16.67 | 51.50 ± 9.85 |
| cuOpt 26.8.0 presolved variables | 40,467 | 43,033 |
| cuOpt time to target (s) | 68.99 ± 10.09 | 85.24 ± 11.82 |
| cuOpt solver time (s) | 102.74 ± 8.82 | 108.16 ± 9.90 |

CP-SAT cleared critical requests in two baseline runs and all three
shared-match runs. Both cuOpt formulations cleared them and reached the
configured MIP gap in all three runs. The staged results support further
testing of the CP-SAT formulation. cuOpt reached the score target later
with shared matches on every ward seed.
