# Solvers

Pass a solver code to the CLI with `--solver <code>`. OR-Tools/CP-SAT is the
default and the only recommended backend. Other backends are experimental or
limited.

## Support matrix

### [OR-Tools](https://developers.google.com/optimization)

| Solver | Selector | API | Platforms | Level |
| --- | --- | --- | --- | --- |
| CP-SAT | `ortools/cp-sat` | `cp_model.CpModel` and `CpSolver` | 🐧 🍎 🪟 | Recommended |
| CBC | `ortools/mpsolver/cbc` | `pywraplp.Solver` (MPSolver) | 🐧 🍎 🪟 | Experimental |
| SCIP | `ortools/mpsolver/scip` | `pywraplp.Solver` (MPSolver) | 🐧 🍎 🪟 | Experimental |
| CP-SAT | `ortools/mpsolver/cp-sat` | `pywraplp.Solver` (MPSolver) | 🐧 🍎 🪟 | Experimental |
| BOP | `ortools/mpsolver/bop` | `pywraplp.Solver` (MPSolver) | 🐧 🍎 🪟 | Limited |
| GSCIP | `ortools/mathopt/gscip` | `mathopt.Model` | 🐧 🍎 🪟 | Experimental |
| CP-SAT | `ortools/mathopt/cp-sat` | `mathopt.Model` | 🐧 🍎 🪟 | Experimental |
| HiGHS | `ortools/mathopt/highs` | `mathopt.Model` | 🐧 🍎 🪟 | Experimental |

### [PuLP](https://coin-or.github.io/pulp/)

| Solver | Selector | API | Platforms | Level |
| --- | --- | --- | --- | --- |
| CBC | `pulp/cbc` | `pulp.LpProblem` | 🐧 🍎 🪟 | Experimental |
| cuOpt | `pulp/cuopt` | `pulp.LpProblem` | 🐧 | Experimental |
| GLPK | `pulp/glpk` | `pulp.LpProblem` | 🐧 🍎 🪟 | Limited |
| HiGHS | `pulp/highs` | `pulp.LpProblem` | 🐧 🪟 | Experimental |
| SCIP | `pulp/scip` | `pulp.LpProblem` | 🐧 🪟 | Experimental |

🐧 is Linux, 🍎 is macOS, and 🪟 is Windows. Only validated platforms are
shown.

Recommended is the default. Experimental is tested but not recommended.
Limited is intended only for small or bounded cases.

- Linux and Windows coverage is x86_64 only. ARM validation is pending.
- PuLP/cuOpt is tested on Linux and requires the NVIDIA cuOpt runtime and a
  supported GPU. macOS has no supported GPU runtime. Windows validation is
  pending.
- PuLP/GLPK requires `glpsol`.
- PuLP/GLPK uses smoke coverage because some full regression models take
  several minutes without proving optimality.
- PuLP/HiGHS is skipped on macOS because its native library may conflict with the HiGHS library bundled with OR-Tools in the same Python process. Observed failure in GitHub runners, should investigate further in the future.
- PuLP/SCIP validation on macOS is pending.
- MPSolver/BOP is a legacy engine intended only for small cases.

## Test coverage

Test filenames below are relative to `core/tests/`.

### Low-level tests

| API | Test File |
| --- | --- |
| OR-Tools CP-SAT | `test_solver_ortools_cp_sat.py` |
| OR-Tools MPSolver | `test_solver_ortools_linear.py` |
| OR-Tools MathOpt | `test_solver_ortools_mathopt.py` |
| PuLP/CBC | `test_solver_pulp_cbc.py` |
| PuLP/cuOpt | `test_solver_pulp_cuopt.py`, skipped in CI |
| PuLP/GLPK | `test_solver_pulp_glpk.py` |
| PuLP/HiGHS and SCIP | `test_solver_pulp_python.py` |

### Schedule tests

| Selector | Coverage | Test File | Real Test |
| --- | --- | --- | --- |
| `ortools/cp-sat` | Full | `test_schedule_ortools_cp_sat.py` | `real/schedule_ortools_cp_sat.py` |
| `ortools/mpsolver/cbc` | Basic | `test_schedule_ortools_mpsolver_cbc.py` | — |
| `ortools/mpsolver/scip` | Basic | `test_schedule_ortools_mpsolver_scip.py` | — |
| `ortools/mpsolver/cp-sat` | Basic | `test_schedule_ortools_mpsolver_cp_sat.py` | — |
| `ortools/mpsolver/bop` | Smoke | `test_schedule_ortools_mpsolver_bop.py` | — |
| `ortools/mathopt/gscip` | Basic | `test_schedule_ortools_mathopt_gscip.py` | — |
| `ortools/mathopt/cp-sat` | Basic | `test_schedule_ortools_mathopt_cp_sat.py` | — |
| `ortools/mathopt/highs` | Basic | `test_schedule_ortools_mathopt_highs.py` | — |
| `pulp/cbc` | Basic and XLSX | `test_schedule_pulp_cbc.py`, `test_export_xlsx_pulp_cbc.py` | `real/schedule_pulp_cbc.py`, skipped |
| `pulp/cuopt` | Basic, skipped in CI | `test_schedule_pulp_cuopt.py` | `real/schedule_pulp_cuopt.py`, skipped |
| `pulp/glpk` | Smoke | `test_schedule_pulp_glpk.py` | — |
| `pulp/highs` | Basic, skipped on macOS | `test_schedule_pulp_highs.py` | — |
| `pulp/scip` | Basic | `test_schedule_pulp_scip.py` | — |

Full coverage includes Basic coverage and an enabled real-scenario test. Basic
coverage runs every non-real YAML fixture. It normally solves each valid case
again while avoiding the first solution, then checks the expected schedule.
Smoke coverage uses one representative scenario with a fixed timeout. Tests
under `core/tests/real/` are explicit, slower checks outside the normal test
discovery rules.

## Excluded backends

Commercial or proprietary integrations such as CPLEX, Gurobi, MOSEK, XPRESS,
COPT, SAS, and MIPCL are intentionally excluded from the standard environment.

### OR-Tools

- Continuous solvers such as GLOP, CLP, and PDLP cannot represent this
  project's binary and integer scheduling model.
- MathOpt/GLPK is not bundled in the OR-Tools Python wheel. GLPK is exposed
  through PuLP instead.
- Additional aliases for the same engine are omitted unless they provide a
  useful API or test boundary.

### PuLP

- CyLP is excluded because PuLP 3.3.2 loses the maximization sense while
  passing its MPS model to CyLP, which can return a minimized schedule as
  “Optimal.”
- `COIN_CMD`, `HiGHS_CMD`, `SCIP_CMD`, and `FSCIP_CMD` require separate
  executables and mostly duplicate supported CBC, HiGHS, and SCIP engines.
- `PYGLPK` and `COINMP_DLL` are unavailable legacy integrations. GLPK is
  supported through `GLPK_CMD`.
- `CHOCO_CMD` requires Java and a separately managed parser JAR, neither of
  which is part of the project environment.
- PuLP's CP-SAT integration is not present in the pinned PuLP 3.3.2 release.
  The native OR-Tools/CP-SAT backend is already the recommended default.
