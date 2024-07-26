from . import utils
from .context import Context

def all_requirements_fulfilled(ctx: Context, args, preference_id):
    # Hard constraint
    # For all shifts, the requirements (# of people) must be fulfilled.
    # Note that a shift is represented as (d, r)
    # i.e., sum_{p}(shifts[(d, r, p)]) == required_n_people, for all (d, r)
    for (d, r), ps in ctx.map_dr_p.items():
        actual_n_people = sum(ctx.shifts[(d, r, p)] for p in ps)
        required_n_people = utils.required_n_people(ctx.requirements[r])
        ctx.model.Add(actual_n_people == required_n_people)

def all_people_work_at_most_one_shift_per_day(ctx: Context, args, preference_id):
    # Hard constraint
    # For all people, for all days, only work at most one shift.
    # Note that a shift in day `d` can be represented as `r` instead of (d, r).
    # i.e., sum_{r}(shifts[(d, r, p)]) <= 1, for all (d, p)
    for (d, p), rs in ctx.map_dp_r.items():
        actual_n_shifts = sum(ctx.shifts[(d, r, p)] for r in rs)
        maximum_n_shifts = 1
        ctx.model.Add(actual_n_shifts <= maximum_n_shifts)

def assign_shifts_evenly(ctx: Context, args, preference_id):
    # Soft constraint
    # For all people, spread the shifts evenly.
    # Note that a shift is represented as (d, r)
    # i.e., max(weight * (actual_n_shifts - target_n_shifts) ** 2), for all p,
    # where actual_n_shifts = sum_{(d, r)}(shifts[(d, r, p)])
    for p in range(ctx.n_people):
        actual_n_shifts = sum(ctx.shifts[(d, r, p)] for d, r in ctx.map_p_dr[p])
        target_n_shifts = round(ctx.n_days * sum(requirement.required_people for requirement in ctx.requirements) / ctx.n_people)
        unique_var_prefix = f"pref_{preference_id}_p_{p}_"

        # Construct: L2 = actual_n_shifts - target_n_shifts) ** 2
        L, U = -100, 100 # TODO: Calculate the actual bounds
        diff_var_name = f"{unique_var_prefix}_diff"
        ctx.model_vars[diff_var_name] = diff = ctx.model.NewIntVar(L, U, diff_var_name)
        ctx.model.Add(diff == (actual_n_shifts - target_n_shifts))
        L2_var_name = f"{unique_var_prefix}_L2"
        ctx.model_vars[L2_var_name] = L2 = ctx.model.NewIntVar(0, max(L**2, U**2), L2_var_name)
        ctx.model.AddMultiplicationEquality(L2, diff, diff)

        # Add the objective
        weight = -1
        ctx.objective += weight * L2

PREFERENCE_TYPES_TO_FUNC = {
    "all requirements fulfilled": all_requirements_fulfilled,
    "all people work at most one shift per day": all_people_work_at_most_one_shift_per_day,
    "assign shifts evenly": assign_shifts_evenly,
}
