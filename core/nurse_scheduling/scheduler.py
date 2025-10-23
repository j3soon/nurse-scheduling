import itertools
import logging
import time
from datetime import timedelta

from ortools.sat.python import cp_model

from . import exporter, preference_types
from .context import Context
from .utils import ortools_expression_to_bool_var, parse_dates, MAP_DATE_KEYWORD_TO_FILTER, MAP_WEEKDAY_TO_STR
from .constants import ALL, OFF, OFF_sid
from .loader import load_data

def schedule(filepath: str, deterministic=False, avoid_solution=None, prettify=False, timeout: int | None = None):
    logging.info(f"Loading scenario from '{filepath}'...")
    scenario = load_data(filepath)

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

    logging.info("Creating shift variables...")
    # Ref: https://developers.google.com/optimization/scheduling/employee_scheduling
    # In the following code, we always use the convention of (d, s, p)
    # to represent the index of (day, shift_type, person).
    # The object will not be abbreviated as (d, s, p) to avoid confusion.
    for d in range(ctx.n_days):
        for s in range(ctx.n_shift_types):
            for p in range(ctx.n_people):
                var_name = f"shift_d{d}_s{s}_p{p}"
                ctx.model_vars[var_name] = ctx.shifts[(d, s, p)] = ctx.model.NewBoolVar(var_name)

    if avoid_solution is not None:
        avoid_solution_vars = []
        logging.info("Avoiding solution...")
        for (d, s, p) in ctx.shifts:
            if avoid_solution[(d, s, p)] == 0:
                avoid_solution_vars.append(ctx.shifts[(d, s, p)])
            elif avoid_solution[(d, s, p)] == 1:
                avoid_solution_vars.append(ctx.shifts[(d, s, p)].Not())
            else:
                raise ValueError(f"Invalid value: {avoid_solution[(d, s, p)]}")
        # Add constraint that at least one variable must be different from the solution to avoid
        ctx.model.AddBoolOr(avoid_solution_vars)

    logging.info("Creating off variables...")
    for d in range(ctx.n_days):
        for p in range(ctx.n_people):
            dp_shifts_sum = sum(ctx.shifts[(d, s, p)] for s in range(ctx.n_shift_types))
            var_name = f"off_d{d}_p{p}"
            ctx.model_vars[var_name] = ctx.offs[(d, p)] = ortools_expression_to_bool_var(
                ctx.model, var_name,
                dp_shifts_sum == 0,
                dp_shifts_sum != 0,
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
    ctx.model.Maximize(ctx.objective)

    logging.info("Initializing solver...")
    solver = cp_model.CpSolver()
    if deterministic:
        logging.info("Configuring deterministic solver...")
        solver.parameters.random_seed = 0
        solver.parameters.num_workers = 1
        # Potentially related parameters are:
        # `random_seed`, `num_workers`, and `num_search_workers`
        # Ref: https://github.com/google/or-tools/blob/stable/ortools/sat/sat_parameters.proto
        # ctx.model.add_decision_strategy(list(ctx.shifts.values()), cp_model.CHOOSE_FIRST, cp_model.SELECT_MIN_VALUE)

    class PartialSolutionPrinter(cp_model.CpSolverSolutionCallback):
        """Print intermediate solutions."""
        def __init__(self):
            cp_model.CpSolverSolutionCallback.__init__(self)
            self.n_solutions = 0
            self.best_score = float("-inf")
            self.start_time = time.time()

        def on_solution_callback(self):
            current_score = self.Value(ctx.objective)
            elapsed_time = time.time() - self.start_time
            self.n_solutions += 1
            if current_score > self.best_score:
                self.best_score = current_score
                self.n_solutions = 1
            logging.info(f"# of (best) solutions found: {self.n_solutions}")
            logging.info(f"current score: {current_score}")
            logging.info(f"elapsed time: {elapsed_time:.2f}s")
    solution_printer = PartialSolutionPrinter()

    # Configure timeout (max_time_in_seconds) if provided
    if timeout is not None:
        try:
            solver.parameters.max_time_in_seconds = float(timeout)
            logging.info(f"Solver time limit set to {timeout} seconds")
        except Exception:
            logging.warning("Unable to set solver timeout parameter; proceeding without time limit")

    logging.info("Solving and showing partial results...")
    # The CpSolver will respect max_time_in_seconds and return when the time limit is reached.
    status = solver.Solve(ctx.model, solution_printer)

    logging.info(f"Status: {solver.StatusName(status)}")

    found = status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    # Ref: https://developers.google.com/optimization/cp/cp_solver
    if status == cp_model.OPTIMAL:
        logging.info("Optimal solution found!")
    elif status == cp_model.FEASIBLE:
        logging.info("Feasible solution found!")
    elif status == cp_model.INFEASIBLE:
        logging.info("Proven infeasible!")
    elif status == cp_model.MODEL_INVALID:
        logging.info("Model invalid!")
        logging.info("Validation Info:")
        logging.info(ctx.model.Validate())
    else:
        logging.info("No solution found!")
        raise ValueError(f"No solution found! Status: {solver.StatusName(status)}")
    ctx.solver_status = solver.StatusName(status)

    logging.info("Statistics:")
    logging.info(f"  - conflicts: {solver.NumConflicts()}")
    logging.info(f"  - branches : {solver.NumBranches()}")
    logging.info(f"  - wall time: {solver.WallTime()}s")
    logging.debug("Variables:")
    for k, v in ctx.model_vars.items():
        try:
            logging.debug(f"  - {k}: {solver.Value(v)}")
        except Exception as e:
            logging.debug(f"  - {k}: [Error: {e}]")
    logging.debug("Reports:")
    for report in ctx.reports:
        val = solver.Value(report.variable)
        if report.skip_condition(val):
            continue
        logging.debug(f"  - {report.description}: {val}")

    logging.info(f"Done.")

    if not found:
        return None, None, None, ctx.solver_status, None

    df, cell_export_info = exporter.get_people_versus_date_dataframe(ctx, solver, prettify=prettify)
    solution = {}
    for (d, s, p) in ctx.shifts:
        solution[(d, s, p)] = solver.Value(ctx.shifts[(d, s, p)])
    # TODO: Better way to return?
    return df, solution, solver.Value(ctx.objective), ctx.solver_status, cell_export_info
