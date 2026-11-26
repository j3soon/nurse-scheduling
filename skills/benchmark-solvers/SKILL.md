---
name: benchmark-solvers
description: Compare solver versions, model formulations, or solver settings on this repository's real Schedule Specs. Use for paired cuOpt and OR-Tools CP-SAT benchmarks, score and runtime comparisons, and solver upgrade performance checks.
---

<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- SPDX-FileCopyrightText: 2026 Johnson Sun -->
<!-- This file is mostly AI generated. -->

# Benchmark Solvers

Use the [real-case fixtures and benchmark documentation](../../core/tests/real/README.md).
For the 87-person ward, the existing score target is `4_470_000_000_000`.
Use the real-case wrapper when counting critical request notes. It adds export
formatting without changing the optimization problem.

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
