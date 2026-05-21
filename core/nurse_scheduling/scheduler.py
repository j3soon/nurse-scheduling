"""Main scheduling pipeline: parse input, build model, solve, and export."""

# This file is part of Nurse Scheduling Project, see <https://github.com/j3soon/nurse-scheduling>.
#
# Copyright (C) 2023-2026 Johnson Sun
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import itertools
import logging
from datetime import timedelta

from . import exporter, preference_types
from .constants import ALL, OFF, OFF_sid, Operator, MAP_DATE_KEYWORD_TO_FILTER, MAP_WEEKDAY_TO_STR
from .context import Context
from .utils import parse_dates
from .loader import load_data
from .solver_interface import SolverStatus


def _topo_sort_groups(groups, kind):
    """Return group ids ordered so each group is preceded by any groups it
    references in its `members`. Raises ValueError on cycles.
    """
    by_id = {g.id: g for g in groups}
    group_ids = set(by_id)
    resolved = []
    state = {}  # gid -> 0 unvisited, 1 visiting, 2 done

    def visit(gid, stack):
        s = state.get(gid, 0)
        if s == 2:
            return
        if s == 1:
            cycle = " -> ".join(stack + [gid])
            raise ValueError(
                f"Cycle detected in {kind} group dependencies: {cycle}"
            )
        state[gid] = 1
        for member in by_id[gid].members:
            if member in group_ids and member != gid:
                visit(member, stack + [gid])
        state[gid] = 2
        resolved.append(gid)

    for g in groups:
        visit(g.id, [])
    return resolved, by_id, group_ids


def _resolve_id_groups(groups, id_map, kind):
    """Resolve `groups` whose members reference existing keys in `id_map` or
    other groups in `groups`. Validates references up-front and resolves in
    dependency order so declaration order does not matter.
    """
    if not groups:
        return
    resolved, by_id, group_ids = _topo_sort_groups(groups, kind)
    # Validate references up-front for a clear error message.
    for group in groups:
        for member in group.members:
            if member not in id_map and member not in group_ids:
                raise ValueError(
                    f"{kind} group '{group.id}' references unknown id '{member}'"
                )
    for gid in resolved:
        group = by_id[gid]
        id_map[gid] = sorted(set().union(*[id_map[m] for m in group.members]))


def _resolve_date_groups(groups, id_map, date_range):
    """Resolve date groups in dependency order. Members that are not group ids
    and not already in `id_map` are passed through `parse_dates` as before.
    """
    if not groups:
        return
    resolved, by_id, group_ids = _topo_sort_groups(groups, "date")
    for gid in resolved:
        group = by_id[gid]
        date_indices = set()
        for member in group.members:
            if member in id_map:
                date_indices.update(id_map[member])
            else:
                try:
                    date_indices.update(parse_dates(member, id_map, date_range))
                except Exception as e:
                    raise ValueError(
                        f"date group '{gid}' references unknown member '{member}': {e}"
                    )
        id_map[gid] = sorted(date_indices)


def schedule(
    file_content: bytes,
    deterministic=False,
    avoid_solution=None,
    prettify=False,
    timeout: int | None = None,
    solver: str = 'ortools/cp-sat',
):
    logging.info("Loading scenario from file content...")
    scenario = load_data(file_content)

    logging.info("Extracting scenario data...")
    if scenario.apiVersion != "alpha":
        raise NotImplementedError(f"Unsupported API version: {scenario.apiVersion}")
    ctx = Context(**dict(scenario))
    del scenario
    ctx.n_days = (ctx.dates.range.endDate - ctx.dates.range.startDate).days + 1
    ctx.n_shift_types = len(ctx.shiftTypes.items)
    ctx.n_people = len(ctx.people.items)
    ctx.dates.items = [ctx.dates.range.startDate + timedelta(days=d) for d in range(ctx.n_days)]

    # Map shift type ID to shift type index
    for s in range(ctx.n_shift_types):
        ctx.map_sid_s[ctx.shiftTypes.items[s].id] = [s]
    # Add shift type ALL and OFF keywords
    ctx.map_sid_s[ALL] = list(range(ctx.n_shift_types))
    ctx.map_sid_s[OFF] = [OFF_sid]
    # Map shift type group ID to list of shift type indices
    # Resolved in dependency order with validation so a group can reference
    # other groups regardless of declaration order, and unknown ids raise a
    # clear ValueError instead of an opaque KeyError.
    _resolve_id_groups(ctx.shiftTypes.groups, ctx.map_sid_s, kind="shift type")
    # Map person ID to person index
    for p in range(ctx.n_people):
        ctx.map_pid_p[ctx.people.items[p].id] = [p]
    # Add people ALL keyword
    ctx.map_pid_p[ALL] = list(range(ctx.n_people))
    # Map people group ID to list of person indices
    # See note above on shift type groups.
    _resolve_id_groups(ctx.people.groups, ctx.map_pid_p, kind="people")

    # Map date string (YYYY-MM-DD) to date index
    if ctx.country is not None and ctx.country != 'TW':
        raise ValueError(f"Country {ctx.country} is not supported yet")
    for d in range(ctx.n_days):
        date_obj = ctx.dates.items[d]
        ctx.map_did_d[str(date_obj)] = [d]
    # Add date keywords
    for keyword in MAP_DATE_KEYWORD_TO_FILTER:
        ctx.map_did_d[keyword] = [d for d in range(ctx.n_days) if MAP_DATE_KEYWORD_TO_FILTER[keyword](ctx.dates.items[d])]
    for keyword in MAP_WEEKDAY_TO_STR:
        weekday_index = MAP_WEEKDAY_TO_STR.index(keyword)
        ctx.map_did_d[keyword] = [d for d in range(ctx.n_days) if ctx.dates.items[d].weekday() == weekday_index]
    # Map date group ID to list of date indices
    # Resolved in dependency order so a date group can reference other date
    # groups regardless of declaration order. Non-group members continue to
    # fall back to parse_dates.
    _resolve_date_groups(ctx.dates.groups, ctx.map_did_d, ctx.dates.range)

    logging.info("Initializing solver model...")
    
    solver_backend, solver_engine = solver.lower().split("/", maxsplit=1)

    # Initialize the solver based on backend provider + engine
    if solver_backend == 'ortools' and solver_engine == 'cp-sat':
        from .solver_ortools_cp_sat import ORToolsSolver
        logging.info("Using solver backend=%s engine=%s", solver_backend, solver_engine)
        ctx.solver = ORToolsSolver()
    elif solver_backend == 'pulp' and solver_engine == 'cbc':
        from .solver_pulp_cbc import PuLPSolver
        logging.info("Using solver backend=%s engine=%s", solver_backend, solver_engine)
        ctx.solver = PuLPSolver()
    elif solver_backend == 'pulp' and solver_engine == 'cuopt':
        from .solver_pulp_cuopt import PuLPCuOptSolver
        logging.info("Using solver backend=%s engine=%s", solver_backend, solver_engine)
        ctx.solver = PuLPCuOptSolver()
    else:
        raise ValueError(
            f"Unsupported solver configuration: backend={solver_backend!r}, engine={solver_engine!r}"
        )

    logging.info("Creating shift variables...")
    # Ref: https://developers.google.com/optimization/scheduling/employee_scheduling
    # In the following code, we always use the convention of (d, s, p)
    # to represent the index of (day, shift_type, person).
    # The object will not be abbreviated as (d, s, p) to avoid confusion.
    for d in range(ctx.n_days):
        for s in range(ctx.n_shift_types):
            for p in range(ctx.n_people):
                var_name = f"shift_d{d}_s{s}_p{p}"
                ctx.model_vars[var_name] = ctx.shifts[(d, s, p)] = ctx.solver.new_bool_var(var_name)

    if avoid_solution is not None:
        avoid_solution_vars = []
        logging.info("Avoiding solution...")
        for (d, s, p) in ctx.shifts:
            if avoid_solution[(d, s, p)] == 0:
                avoid_solution_vars.append(ctx.shifts[(d, s, p)])
            elif avoid_solution[(d, s, p)] == 1:
                avoid_solution_vars.append(ctx.solver.negate(ctx.shifts[(d, s, p)]))
            else:
                raise ValueError(f"Invalid value: {avoid_solution[(d, s, p)]}")
        # Add constraint that at least one variable must be different from the solution to avoid
        ctx.solver.add_bool_or(avoid_solution_vars)

    logging.info("Creating off variables...")
    for d in range(ctx.n_days):
        for p in range(ctx.n_people):
            dp_shifts_sum = sum(ctx.shifts[(d, s, p)] for s in range(ctx.n_shift_types))
            var_name = f"off_d{d}_p{p}"
            ctx.model_vars[var_name] = ctx.offs[(d, p)] = ctx.solver.create_bool_var_with_constraint(
                var_name,
                dp_shifts_sum, Operator.EQ, 0,
                (0, ctx.n_shift_types),  # we do not assume "at most one shift per day" here
            )

    logging.info("Creating maps for faster lookup...")
    ctx.map_ds_p = {
        (d, s): {p for p in range(ctx.n_people) if (d, s, p) in ctx.shifts}
        for (d, s) in itertools.product(range(ctx.n_days), range(ctx.n_shift_types))
    }
    ctx.map_dp_s = {
        (d, p): {s for s in range(ctx.n_shift_types) if (d, s, p) in ctx.shifts}
        for (d, p) in itertools.product(range(ctx.n_days), range(ctx.n_people))
    }
    ctx.map_d_sp = {
        d: {(s, p) for (s, p) in itertools.product(range(ctx.n_shift_types), range(ctx.n_people)) if (d, s, p) in ctx.shifts}
        for d in range(ctx.n_days)
    }
    ctx.map_s_dp = {
        s: {(d, p) for (d, p) in itertools.product(range(ctx.n_days), range(ctx.n_people)) if (d, s, p) in ctx.shifts}
        for s in range(ctx.n_shift_types)
    }
    ctx.map_p_ds = {
        p: {(d, s) for (d, s) in itertools.product(range(ctx.n_days), range(ctx.n_shift_types)) if (d, s, p) in ctx.shifts}
        for p in range(ctx.n_people)
    }

    logging.info("Adding preferences (including constraints)...")
    # TODO: Check no duplicated preferences
    # TODO: Check no overlapping preferences
    for i, preference in enumerate(ctx.preferences):
        preference_types.PREFERENCE_TYPES_TO_FUNC[preference.type](ctx, preference, i)

    # Define objective (i.e., soft constraints)
    ctx.solver.set_objective(ctx.objective, maximize=True)

    logging.info("Initializing solver...")
    
    # Create solution callback for tracking intermediate solutions
    solution_callback = ctx.solver.create_solution_callback(ctx.objective)

    logging.info("Solving and showing partial results...")
    status = ctx.solver.solve(timeout=timeout, deterministic=deterministic, solution_callback=solution_callback)

    # Get status name
    ctx.solver_status = ctx.solver.get_status_name()
    logging.info(f"Status: {ctx.solver_status}")

    found = status in (SolverStatus.OPTIMAL, SolverStatus.FEASIBLE)
    # Ref: https://developers.google.com/optimization/cp/cp_solver
    if status == SolverStatus.OPTIMAL:
        logging.info("Optimal solution found!")
    elif status == SolverStatus.FEASIBLE:
        logging.info("Feasible solution found!")
    elif status == SolverStatus.INFEASIBLE:
        logging.info("Proven infeasible!")
    elif status == SolverStatus.MODEL_INVALID:
        logging.info("Model invalid!")
        logging.info("Validation Info:")
        logging.info(ctx.solver.validate_model())
    else:
        logging.info("No solution found!")
        raise ValueError(f"No solution found! Status: {ctx.solver_status}")

    logging.info("Statistics:")
    stats = ctx.solver.get_statistics()
    for key, value in stats.items():
        logging.info(f"  - {key}: {value}")
    
    logging.debug("Variables:")
    for k, v in ctx.model_vars.items():
        try:
            logging.debug(f"  - {k}: {ctx.solver.get_value(v)}")
        except Exception as e:
            logging.debug(f"  - {k}: [Error: {e}]")
    logging.debug("Reports:")
    for report in ctx.reports:
        val = ctx.solver.get_value(report.variable)
        if report.skip_condition(val):
            continue
        logging.debug(f"  - {report.description}: {val}")

    logging.info("Done.")

    if not found:
        return None, None, None, ctx.solver_status, None

    df, cell_export_info = exporter.get_people_versus_date_dataframe(ctx, prettify=prettify)
    solution = {}
    for (d, s, p) in ctx.shifts:
        solution[(d, s, p)] = ctx.solver.get_value(ctx.shifts[(d, s, p)])
    # TODO: Better way to return?
    return df, solution, ctx.solver.get_objective_value(), ctx.solver_status, cell_export_info
