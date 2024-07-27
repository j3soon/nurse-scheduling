from . import utils
from .context import Context
from .report import Report


def all_requirements_fulfilled(ctx: Context, preference, preference_idx):
    # Hard constraint
    # For all shifts, the requirements (# of people) must be fulfilled.
    # Note that a shift is represented as (d, r)
    # i.e., sum_{p}(shifts[(d, r, p)]) == required_n_people, for all (d, r)
    for (d, r), ps in ctx.map_dr_p.items():
        actual_n_people = sum(ctx.shifts[(d, r, p)] for p in ps)
        required_n_people = utils.required_n_people(ctx.requirements[r])
        ctx.model.Add(actual_n_people == required_n_people)

def all_people_work_at_most_one_shift_per_day(ctx: Context, preference, preference_idx):
    # Hard constraint
    # For all people, for all days, only work at most one shift.
    # Note that a shift in day `d` can be represented as `r` instead of (d, r).
    # i.e., sum_{r}(shifts[(d, r, p)]) <= 1, for all (d, p)
    for (d, p), rs in ctx.map_dp_r.items():
        actual_n_shifts = sum(ctx.shifts[(d, r, p)] for r in rs)
        maximum_n_shifts = 1
        ctx.model.Add(actual_n_shifts <= maximum_n_shifts)

def assign_shifts_evenly(ctx: Context, preference, preference_idx):
    # Soft constraint
    # For all people, try to spread the shifts evenly.
    # Note that a shift is represented as (d, r)
    # i.e., max(weight * (actual_n_shifts - target_n_shifts) ** 2), for all p,
    # where actual_n_shifts = sum_{(d, r)}(shifts[(d, r, p)])
    for p in range(ctx.n_people):
        actual_n_shifts = sum(ctx.shifts[(d, r, p)] for d, r in ctx.map_p_dr[p])
        target_n_shifts = round(ctx.n_days * sum(requirement.required_people for requirement in ctx.requirements) / ctx.n_people)
        unique_var_prefix = f"pref_{preference_idx}_p_{p}_"

        # Construct: L2 = actual_n_shifts - target_n_shifts) ** 2
        MAX = max(ctx.n_days - target_n_shifts, target_n_shifts)
        diff_var_name = f"{unique_var_prefix}diff"
        ctx.model_vars[diff_var_name] = diff = ctx.model.NewIntVar(0, MAX, diff_var_name)
        ctx.model.add_abs_equality(diff, actual_n_shifts - target_n_shifts)
        L2_var_name = f"{unique_var_prefix}L2"
        ctx.model_vars[L2_var_name] = L2 = ctx.model.NewIntVar(0, MAX**2, L2_var_name)
        ctx.model.AddMultiplicationEquality(L2, diff, diff)

        # Add the objective
        weight = -1000000
        ctx.objective += weight * L2
        ctx.reports.append(Report(f"assign_shifts_evenly_L2_p_{p}", L2, lambda x: x == 0))

def shift_request(ctx: Context, preference, preference_idx):
    # Soft constraint
    # For all people, try to fulfill the shift requests.
    # Note that a shift is represented as (d, r)
    # i.e., max(weight * shifts[(d, r, p)]), for all satisfying (d, r)
    p = preference.person
    for (d, r) in ctx.map_p_dr[p]:
        # TODO: parse dates
        if (d + 1) not in preference.day:
            continue
        if ctx.requirements[r].id != preference.shift:
            continue
        # Add the objective
        weight = 1
        ctx.objective += weight * ctx.shifts[(d, r, p)]
        ctx.reports.append(Report(f"shift_request_p_{p}_d_{d}_r_{r}", ctx.shifts[(d, r, p)], lambda x: x == 1))

PREFERENCE_TYPES_TO_FUNC = {
    "all requirements fulfilled": all_requirements_fulfilled,
    "all people work at most one shift per day": all_people_work_at_most_one_shift_per_day,
    "assign shifts evenly": assign_shifts_evenly,
    "shift request": shift_request,
}
