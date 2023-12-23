import itertools
import logging
from datetime import timedelta

from ortools.sat.python import cp_model

from . import export, utils
from .dataloader import load_data


def schedule(filepath: str, validate=True, deterministic=False):
    logging.info("Loading scenario from '{filepath}'...")
    scenario = load_data(filepath, validate)

    logging.info("Extracting scenario data...")
    startdate = scenario.startdate
    enddate = scenario.enddate
    requirements = scenario.requirements
    people = scenario.people
    del scenario
    n_days = (enddate - startdate).days + 1
    n_people = len(people)
    n_requirements = len(requirements)
    dates = [startdate + timedelta(days=d) for d in range(n_days)]

    logging.info("Initializing solver model...")
    model = cp_model.CpModel()
    shifts = {}
    """A set of indicator variables that are 1 if and only if
    a person (p) is assigned to a shift (d, r)."""

    logging.info("Creating shift variables...")
    # Ref: https://developers.google.com/optimization/scheduling/employee_scheduling
    for d in range(n_days):
        for r in range(n_requirements):
            for p in range(n_people):
                shifts[(d, r, p)] = model.NewBoolVar(f"shift_d{d}_r{r}_p{p}")

    logging.info("Creating maps for faster lookup...")
    map_dr_p = {
        (d, r): {p for p in range(n_people) if (d, r, p) in shifts}
        for (d, r) in itertools.product(range(n_days), range(n_requirements))
    }
    map_dp_r = {
        (d, p): {r for r in range(n_requirements) if (d, r, p) in shifts}
        for (d, p) in itertools.product(range(n_days), range(n_people))
    }
    map_d_rp = {
        d: {(r, p) for (r, p) in itertools.product(range(n_requirements), range(n_people)) if (d, r, p) in shifts}
        for d in range(n_days)
    }
    map_r_dp = {
        r: {(d, p) for (d, p) in itertools.product(range(n_days), range(n_people)) if (d, r, p) in shifts}
        for r in range(n_requirements)
    }
    map_p_dr = {
        p: {(d, r) for (d, r) in itertools.product(range(n_days), range(n_requirements)) if (d, r, p) in shifts}
        for p in range(n_people)
    }

    logging.info("Adding preferences and constraints...")
    # Hard constraint
    # For all shifts, the requirements (# of people) must be fulfilled.
    # Note that a shift is represented as (d, r)
    # i.e., sum_{p}(shifts[(d, r, p)]) == required_n_people, for all (d, r)
    for (d, r), ps in map_dr_p.items():
        actual_n_people = sum(shifts[(d, r, p)] for p in ps)
        required_n_people = utils.required_n_people(requirements[r])
        model.Add(actual_n_people == required_n_people)

    # Hard constraint
    # For all people, for all days, only work at most one shift.
    # Note that a shift in day `d` can be represented as `r` instead of (d, r).
    # i.e., sum_{r}(shifts[(d, r, p)]) <= 1, for all (d, p)
    for (d, p), rs in map_dp_r.items():
        actual_n_shifts = sum(shifts[(d, r, p)] for r in rs)
        maximum_n_shifts = 1
        model.Add(actual_n_shifts <= maximum_n_shifts)

    logging.info("Initializing solver...")
    solver = cp_model.CpSolver()
    if deterministic:
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
            print("# of solutions found:", self.solution_count)
    solution_printer = PartialSolutionPrinter()

    logging.info("Solving and showing partial results...")
    status = solver.Solve(model, solution_printer)

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
        logging.info(model.Validate())
    else:
        logging.info("No solution found!")

    logging.info("Statistics:")
    logging.info(f"  - conflicts: {solver.NumConflicts()}")
    logging.info(f"  - branches : {solver.NumBranches()}")
    logging.info(f"  - wall time: {solver.WallTime()}s")

    logging.info(f"Done.")

    if not found:
        return None

    df = export.get_people_versus_date_dataframe(
        dates, people, requirements,
        shifts, solver,
    )
    return df
