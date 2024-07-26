from . import utils

def all_requirements_fulfilled(ctx, args):
    # Hard constraint
    # For all shifts, the requirements (# of people) must be fulfilled.
    # Note that a shift is represented as (d, r)
    # i.e., sum_{p}(shifts[(d, r, p)]) == required_n_people, for all (d, r)
    for (d, r), ps in ctx.map_dr_p.items():
        actual_n_people = sum(ctx.shifts[(d, r, p)] for p in ps)
        required_n_people = utils.required_n_people(ctx.requirements[r])
        ctx.model.Add(actual_n_people == required_n_people)

def all_people_work_at_most_one_shift_per_day(ctx, args):
    # Hard constraint
    # For all people, for all days, only work at most one shift.
    # Note that a shift in day `d` can be represented as `r` instead of (d, r).
    # i.e., sum_{r}(shifts[(d, r, p)]) <= 1, for all (d, p)
    for (d, p), rs in ctx.map_dp_r.items():
        actual_n_shifts = sum(ctx.shifts[(d, r, p)] for r in rs)
        maximum_n_shifts = 1
        ctx.model.Add(actual_n_shifts <= maximum_n_shifts)

OBJECTIVE_TYPES_TO_FUNC = {
    "all requirements fulfilled": all_requirements_fulfilled,
    "all people work at most one shift per day": all_people_work_at_most_one_shift_per_day,
}
