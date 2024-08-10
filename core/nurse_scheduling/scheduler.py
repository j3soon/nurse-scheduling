import itertools
import logging
from datetime import timedelta
from typing import List

from ortools.sat.python import cp_model

from . import exporter, preference_types
from .context import Context
from .dataloader import load_data
from .report import Report


def schedule(filepath: str, validate=True, deterministic=False):
    logging.debug(f"Loading scenario from '{filepath}'...")
    scenario = load_data(filepath, validate)

    logging.debug("Extracting scenario data...")
    if scenario.apiVersion != "alpha":
        raise NotImplementedError(f"Unsupported API version: {scenario.apiVersion}")
    ctx = Context()
    ctx.startdate = scenario.startdate
    ctx.enddate = scenario.enddate
    ctx.requirements = scenario.requirements
    ctx.people = scenario.people
    ctx.preferences = scenario.preferences
    del scenario
    ctx.n_days = (ctx.enddate - ctx.startdate).days + 1
    ctx.n_requirements = len(ctx.requirements)
    ctx.n_people = len(ctx.people)
    ctx.dates = [ctx.startdate + timedelta(days=d) for d in range(ctx.n_days)]
    ctx.map_rid_r = {}
    for r in range(ctx.n_requirements):
        if ctx.requirements[r].id in ctx.map_rid_r:
            raise ValueError(f"Duplicated requirement ID: {r.id}")
        ctx.map_rid_r[ctx.requirements[r].id] = r

    logging.debug("Initializing solver model...")
    ctx.model = cp_model.CpModel()
    ctx.model_vars = {}
    ctx.reports: List[Report] = []
    ctx.shifts = {}
    """A set of indicator variables that are 1 if and only if
    a person (p) is assigned to a shift (d, r)."""

    logging.debug("Creating shift variables...")
    # Ref: https://developers.google.com/optimization/scheduling/employee_scheduling
    # In the following code, we always use the convention of (d, r, p)
    # to represent the index of (day, requirement, person).
    # The object will not be abbreviated as (d, r, p) to avoid confusion.
    for d in range(ctx.n_days):
        for r in range(ctx.n_requirements):
            # TODO(Optimize): Skip if no people is required in that day
            for p in range(ctx.n_people):
                # TODO(Optimize): Skip if the person does not qualify for the requirement
                var_name = f"shift_d{d}_r{r}_p{p}"
                ctx.model_vars[var_name] = ctx.shifts[(d, r, p)] = ctx.model.NewBoolVar(var_name)

    logging.debug("Creating maps for faster lookup...")
    ctx.map_dr_p = {
        (d, r): {p for p in range(ctx.n_people) if (d, r, p) in ctx.shifts}
        for (d, r) in itertools.product(range(ctx.n_days), range(ctx.n_requirements))
    }
    ctx.map_dp_r = {
        (d, p): {r for r in range(ctx.n_requirements) if (d, r, p) in ctx.shifts}
        for (d, p) in itertools.product(range(ctx.n_days), range(ctx.n_people))
    }
    ctx.map_d_rp = {
        d: {(r, p) for (r, p) in itertools.product(range(ctx.n_requirements), range(ctx.n_people)) if (d, r, p) in ctx.shifts}
        for d in range(ctx.n_days)
    }
    ctx.map_r_dp = {
        r: {(d, p) for (d, p) in itertools.product(range(ctx.n_days), range(ctx.n_people)) if (d, r, p) in ctx.shifts}
        for r in range(ctx.n_requirements)
    }
    ctx.map_p_dr = {
        p: {(d, r) for (d, r) in itertools.product(range(ctx.n_days), range(ctx.n_requirements)) if (d, r, p) in ctx.shifts}
        for p in range(ctx.n_people)
    }

    ctx.objective = 0

    logging.debug("Adding preferences (including constraints)...")
    # TODO: Check no duplicated preferences
    # TODO: Check no overlapping preferences
    # TODO: Check all required preferences are present
    for i, preference in enumerate(ctx.preferences):
        preference_types.PREFERENCE_TYPES_TO_FUNC[preference.type](ctx, preference, i)

    # Define objective (i.e., soft constraints)
    ctx.model.Maximize(ctx.objective)

    logging.debug("Initializing solver...")
    solver = cp_model.CpSolver()
    if deterministic:
        logging.debug("Configuring deterministic solver...")
        solver.parameters.random_seed = 0
        solver.parameters.num_workers = 1
        # Potentially related parameters are:
        # `random_seed`, `num_workers`, and `num_search_workers`
        # Ref: https://github.com/google/or-tools/blob/stable/ortools/sat/sat_parameters.proto

    class PartialSolutionPrinter(cp_model.CpSolverSolutionCallback):
        """Print intermediate solutions."""
        def __init__(self):
            cp_model.CpSolverSolutionCallback.__init__(self)
            self.solution_count = 0

        def on_solution_callback(self):
            self.solution_count += 1
            logging.debug(f"# of solutions found: {self.solution_count}")
            logging.debug(f"current score: {self.Value(ctx.objective)}")
    solution_printer = PartialSolutionPrinter()

    logging.debug("Solving and showing partial results...")
    status = solver.Solve(ctx.model, solution_printer)

    logging.debug(f"Status: {solver.StatusName(status)}")

    found = status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    # Ref: https://developers.google.com/optimization/cp/cp_solver
    if status == cp_model.OPTIMAL:
        logging.debug("Optimal solution found!")
    elif status == cp_model.FEASIBLE:
        logging.debug("Feasible solution found!")
    elif status == cp_model.INFEASIBLE:
        logging.debug("Proven infeasible!")
    elif status == cp_model.MODEL_INVALID:
        logging.debug("Model invalid!")
        logging.debug("Validation Info:")
        logging.debug(ctx.model.Validate())
    else:
        logging.debug("No solution found!")

    logging.debug("Statistics:")
    logging.debug(f"  - conflicts: {solver.NumConflicts()}")
    logging.debug(f"  - branches : {solver.NumBranches()}")
    logging.debug(f"  - wall time: {solver.WallTime()}s")
    logging.debug("Variables:")
    for k, v in ctx.model_vars.items():
        logging.debug(f"  - {k}: {solver.Value(v)}")
    logging.debug("Reports:")
    for report in ctx.reports:
        val = solver.Value(report.variable)
        if report.skip_condition(val):
            continue
        logging.debug(f"  - {report.description}: {val}")

    logging.debug(f"Done.")

    if not found:
        return None

    df = exporter.get_people_versus_date_dataframe(ctx, solver)
    return df
