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

import logging
import itertools
from dataclasses import replace
from collections.abc import Callable
from datetime import timedelta

from . import exporter, preference_types
from .constants import ALL, OFF, OFF_sid, MAP_DATE_KEYWORD_TO_FILTER, MAP_WEEKDAY_TO_STR
from .context import Context
from .utils import parse_dates
from .loader import load_data
from .model_build_stats import ModelBuildStats, emit_model_build_stats, start_model_build_step
from .solver_interface import SolverProgress, SolverStatus


def schedule(
    file_content: bytes,
    deterministic=False,
    avoid_solution=None,
    prettify=False,
    timeout: int | None = None,
    solver: str = "ortools/cp-sat",
    progress_callback: Callable[[SolverProgress], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
    model_build_stats_callback: Callable[[ModelBuildStats], None] | None = None,
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
    for g in range(len(ctx.shiftTypes.groups)):
        group = ctx.shiftTypes.groups[g]
        # Flatten and deduplicate shift type indices for the group
        ctx.map_sid_s[group.id] = sorted(set().union(*[ctx.map_sid_s[sid] for sid in group.members]))
    # Map person ID to person index
    for p in range(ctx.n_people):
        ctx.map_pid_p[ctx.people.items[p].id] = [p]
    # Add people ALL keyword
    ctx.map_pid_p[ALL] = list(range(ctx.n_people))
    # Map people group ID to list of person indices
    for g in range(len(ctx.people.groups)):
        group = ctx.people.groups[g]
        # Flatten and deduplicate person indices for the group
        ctx.map_pid_p[group.id] = sorted(set().union(*[ctx.map_pid_p[pid] for pid in group.members]))

    # Map date string (YYYY-MM-DD) to date index
    if ctx.country is not None and ctx.country != "TW":
        raise ValueError(f"Country {ctx.country} is not supported yet")
    for d in range(ctx.n_days):
        date_obj = ctx.dates.items[d]
        ctx.map_did_d[str(date_obj)] = [d]
    # Add date keywords
    for keyword in MAP_DATE_KEYWORD_TO_FILTER:
        ctx.map_did_d[keyword] = [
            d for d in range(ctx.n_days) if MAP_DATE_KEYWORD_TO_FILTER[keyword](ctx.dates.items[d])
        ]
    for keyword in MAP_WEEKDAY_TO_STR:
        weekday_index = MAP_WEEKDAY_TO_STR.index(keyword)
        ctx.map_did_d[keyword] = [d for d in range(ctx.n_days) if ctx.dates.items[d].weekday() == weekday_index]
    # Map date group ID to list of date indices
    for g in range(len(ctx.dates.groups)):
        group = ctx.dates.groups[g]
        # Flatten and deduplicate date indices for the group
        date_indices = set()
        for member in group.members:
            if member in ctx.map_did_d:
                date_indices.update(ctx.map_did_d[member])
            else:
                date_indices.update(parse_dates(member, ctx.map_did_d, ctx.dates.range))
        ctx.map_did_d[group.id] = sorted(set(date_indices))

    logging.info("Initializing solver model...")

    solver_backend, solver_engine = solver.lower().split("/", maxsplit=1)

    # Initialize the solver based on backend provider + engine
    if solver_backend == "ortools" and solver_engine == "cp-sat":
        from .solver_ortools_cp_sat import ORToolsSolver

        logging.info("Using solver backend=%s engine=%s", solver_backend, solver_engine)
        ctx.solver = ORToolsSolver()
    elif solver_backend == "pulp" and solver_engine == "cbc":
        from .solver_pulp_cbc import PuLPSolver

        logging.info("Using solver backend=%s engine=%s", solver_backend, solver_engine)
        ctx.solver = PuLPSolver()
    elif solver_backend == "pulp" and solver_engine == "cuopt":
        from .solver_pulp_cuopt import PuLPCuOptSolver

        logging.info("Using solver backend=%s engine=%s", solver_backend, solver_engine)
        ctx.solver = PuLPCuOptSolver()
    else:
        raise ValueError(f"Unsupported solver configuration: backend={solver_backend!r}, engine={solver_engine!r}")

    logging.info("Creating shift variables...")
    step_started_at, start_counts = start_model_build_step(model_build_stats_callback, ctx)
    # Ref: https://developers.google.com/optimization/scheduling/employee_scheduling
    # In the following code, we always use the convention of (d, s, p)
    # to represent the index of (day, shift_type, person).
    # The object will not be abbreviated as (d, s, p) to avoid confusion.
    for d in range(ctx.n_days):
        for s in range(ctx.n_shift_types):
            for p in range(ctx.n_people):
                var_name = f"shift_d{d}_s{s}_p{p}"
                ctx.model_vars[var_name] = ctx.shifts[(d, s, p)] = ctx.solver.new_bool_var(var_name)
    emit_model_build_stats(
        model_build_stats_callback,
        ctx,
        "create_shift_variables",
        step_started_at,
        start_counts,
    )

    if avoid_solution is not None:
        step_started_at, start_counts = start_model_build_step(model_build_stats_callback, ctx)
        avoid_solution_vars = []
        logging.info("Avoiding solution...")
        for d, s, p in ctx.shifts:
            if avoid_solution[(d, s, p)] == 0:
                avoid_solution_vars.append(ctx.shifts[(d, s, p)])
            elif avoid_solution[(d, s, p)] == 1:
                avoid_solution_vars.append(ctx.solver.negate(ctx.shifts[(d, s, p)]))
            else:
                raise ValueError(f"Invalid value: {avoid_solution[(d, s, p)]}")
        # Add constraint that at least one variable must be different from the solution to avoid
        ctx.solver.add_bool_or(avoid_solution_vars)
        emit_model_build_stats(
            model_build_stats_callback,
            ctx,
            "avoid_solution",
            step_started_at,
            start_counts,
        )

    logging.info("Creating off variables...")
    step_started_at, start_counts = start_model_build_step(model_build_stats_callback, ctx)
    for d in range(ctx.n_days):
        for p in range(ctx.n_people):
            dp_shifts_sum = sum(ctx.shifts[(d, s, p)] for s in range(ctx.n_shift_types))
            var_name = f"off_d{d}_p{p}"
            ctx.model_vars[var_name] = ctx.offs[(d, p)] = ctx.solver.new_bool_var(var_name)
            # This defines OFF and enforces at most one shift per person per day.
            # Previously, OFF was defined separately as:
            #   ctx.solver.create_bool_var_with_constraint(
            #       var_name, dp_shifts_sum, Operator.EQ, 0, (0, ctx.n_shift_types)
            #   )
            # and the at-most-one preference added:
            #   dp_shifts_sum <= 1
            ctx.solver.add_constraint(ctx.offs[(d, p)] + dp_shifts_sum == 1)
    emit_model_build_stats(
        model_build_stats_callback,
        ctx,
        "create_off_variables",
        step_started_at,
        start_counts,
    )

    logging.info("Creating maps for faster lookup...")
    step_started_at, start_counts = start_model_build_step(model_build_stats_callback, ctx)
    # TODO: All shift combinations exist, so these membership checks can be removed
    # if model-build overhead becomes significant.
    ctx.map_ds_p = {
        (d, s): {p for p in range(ctx.n_people) if (d, s, p) in ctx.shifts}
        for (d, s) in itertools.product(range(ctx.n_days), range(ctx.n_shift_types))
    }
    ctx.map_dp_s = {
        (d, p): {s for s in range(ctx.n_shift_types) if (d, s, p) in ctx.shifts}
        for (d, p) in itertools.product(range(ctx.n_days), range(ctx.n_people))
    }
    ctx.map_d_sp = {
        d: {
            (s, p)
            for (s, p) in itertools.product(range(ctx.n_shift_types), range(ctx.n_people))
            if (d, s, p) in ctx.shifts
        }
        for d in range(ctx.n_days)
    }
    ctx.map_s_dp = {
        s: {(d, p) for (d, p) in itertools.product(range(ctx.n_days), range(ctx.n_people)) if (d, s, p) in ctx.shifts}
        for s in range(ctx.n_shift_types)
    }
    ctx.map_p_ds = {
        p: {
            (d, s)
            for (d, s) in itertools.product(range(ctx.n_days), range(ctx.n_shift_types))
            if (d, s, p) in ctx.shifts
        }
        for p in range(ctx.n_people)
    }
    emit_model_build_stats(
        model_build_stats_callback,
        ctx,
        "create_lookup_maps",
        step_started_at,
        start_counts,
    )

    logging.info("Adding preferences (including constraints)...")
    # TODO: Check no duplicated preferences
    # TODO: Check no overlapping preferences
    for i, preference in enumerate(ctx.preferences):
        step_started_at, start_counts = start_model_build_step(
            model_build_stats_callback,
            ctx,
        )
        preference_types.PREFERENCE_TYPES_TO_FUNC[preference.type](ctx, preference, i)
        emit_model_build_stats(
            model_build_stats_callback,
            ctx,
            "add_preference",
            step_started_at,
            start_counts,
            preference_index=i,
            preference_type=preference.type,
        )

    # Define objective (i.e., soft constraints)
    ctx.solver.set_objective(ctx.objective, maximize=True)

    logging.info("Initializing solver...")

    if prettify and progress_callback is not None:

        def progress_callback_with_export(payload: SolverProgress) -> None:
            df, cell_export_info = exporter.get_people_versus_date_dataframe(ctx, prettify=True)
            progress_callback(replace(payload, df=df, cell_export_info=cell_export_info))

    else:
        progress_callback_with_export = progress_callback

    logging.info("Solving and showing partial results...")
    status = ctx.solver.solve(
        timeout=timeout,
        deterministic=deterministic,
        progress_callback=progress_callback_with_export,
        should_stop=should_stop,
    )

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
    for d, s, p in ctx.shifts:
        solution[(d, s, p)] = ctx.solver.get_value(ctx.shifts[(d, s, p)])
    # TODO: Better way to return?
    return df, solution, ctx.solver.get_objective_value(), ctx.solver_status, cell_export_info
