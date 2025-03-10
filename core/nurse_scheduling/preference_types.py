import itertools
from . import utils
from .context import Context
from .report import Report

# Leave most parsing to the caller, keep the function here simple.

def shift_type_requirements(ctx: Context, preference, preference_idx):
    # Hard constraint
    # For all shift types, the requirements (# of people) must be fulfilled.
    # Note that a shift is represented as (d, s)
    # i.e., sum_{p}(shifts[(d, s, p)]) == required_num_people, for all (d, s)
    
    ss = utils.parse_sids(preference.shift_type, ctx.map_sid_s)
    for d in range(ctx.n_days):
        for s in ss:
            ps = ctx.map_ds_p[(d, s)]
            ctx.model.Add(sum(ctx.shifts[(d, s, p)] for p in ps) == preference.required_num_people)

def all_people_work_at_most_one_shift_per_day(ctx: Context, preference, preference_idx):
    # Hard constraint
    # For all people, for all days, only work at most one shift.
    # Note that a shift in day `d` can be represented as `s` instead of (d, s).
    # i.e., sum_{s}(shifts[(d, s, p)]) <= 1, for all (d, p)
    for (d, p), ss in ctx.map_dp_s.items():
        actual_n_shifts = sum(ctx.shifts[(d, s, p)] for s in ss)
        maximum_n_shifts = 1
        ctx.model.Add(actual_n_shifts <= maximum_n_shifts)

def assign_shifts_evenly(ctx: Context, preference, preference_idx):
    # Soft constraint
    # For all people, try to spread the shifts evenly.
    # Note that a shift is represented as (d, s)
    # i.e., max(weight * (actual_n_shifts - target_n_shifts) ** 2), for all p,
    # where actual_n_shifts = sum_{(d, s)}(shifts[(d, s, p)])
    total_shifts = 0
    for pref in ctx.preferences:
        if pref.type == "shift type requirement":
            shift_types = utils.parse_sids(pref.shift_type, ctx.map_sid_s)
            total_shifts += pref.required_num_people * len(shift_types) * ctx.n_days
    
    for p in range(ctx.n_people):
        actual_n_shifts = sum(ctx.shifts[(d, s, p)] for d, s in ctx.map_p_ds[p])
        target_n_shifts = round(total_shifts / ctx.n_people)
        unique_var_prefix = f"pref_{preference_idx}_p_{p}_"

        # Construct: L2 = (actual_n_shifts - target_n_shifts) ** 2
        MAX = max(ctx.n_days - target_n_shifts, target_n_shifts)
        diff_var_name = f"{unique_var_prefix}diff"
        ctx.model_vars[diff_var_name] = diff = ctx.model.NewIntVar(0, MAX, diff_var_name)
        ctx.model.add_abs_equality(diff, actual_n_shifts - target_n_shifts)
        L2_var_name = f"{unique_var_prefix}L2"
        ctx.model_vars[L2_var_name] = L2 = ctx.model.NewIntVar(0, MAX**2, L2_var_name)
        ctx.model.AddMultiplicationEquality(L2, diff, diff)

        # Add the objective
        weight = preference.weight
        ctx.objective += weight * L2
        ctx.reports.append(Report(f"assign_shifts_evenly_L2_p_{p}", L2, lambda x: x == 0))

def shift_request(ctx: Context, preference, preference_idx):
    # Soft constraint
    # For all people, try to fulfill the shift requests.
    # Note that a shift is represented as (d, s)
    # i.e., max(weight * shifts[(d, s, p)]), for all satisfying (d, s)
    dates = utils.parse_dates(preference.date, ctx.startdate, ctx.enddate)
    ss = utils.parse_sids(preference.shift_type, ctx.map_sid_s)
    ps = utils.parse_pids(preference.person, ctx.map_pid_p)
    for date in dates:
        d = (date - ctx.startdate).days
        for s in ss:
            for p in ps:
                # Add the objective
                weight = preference.weight
                ctx.objective += weight * ctx.shifts[(d, s, p)]
                ctx.reports.append(Report(f"shift_request_d_{d}_s_{s}_p_{p}", ctx.shifts[(d, s, p)], lambda x: x == 1))

def unwanted_shift_type_successions(ctx: Context, preference, preference_idx):
    # Soft constraint
    # For all people, for all start date, try to avoid unwanted shift type successions.
    # Note that a shift is represented as (d, s)
    # i.e., max(weight * (actual_n_matched == target_n_matched)), for all p,
    # where actual_n_matched = sum_{(d, s)}(shifts[(d, s, p)]), for all satisfying (d, s)
    ps = utils.parse_pids(preference.person, ctx.map_pid_p)
    pattern = preference.pattern
    if not isinstance(pattern, list):
        raise ValueError(f"Pattern must be a list, but got {type(pattern)}")
    for p in ps:
        # TODO: Consider history
        for d_begin in range(ctx.n_days - len(pattern) + 1):
            # For each day and pattern, collect all matched shifts
            match_shifts_in_day = [
                [ctx.shifts[(d_begin+i, s, p)] for s in ctx.map_dp_s[(d_begin+i, p)]
                if ctx.shift_types[s].id == pattern[i]]
                for i in range(len(pattern))
            ]
            target_n_matched = len(pattern)
            for idx, seq in enumerate(itertools.product(*match_shifts_in_day)):
                assert len(seq) == len(pattern)
                # Construct: is_match = (actual_n_matched == target_n_matched)
                unique_var_prefix = f"unwanted_shift_type_successions_pref_{preference_idx}_p_{p}_dbegin_{d_begin}_seq_{idx}"
                is_match_var_name = f"{unique_var_prefix}_is_match"
                actual_n_matched = sum(seq)
                ctx.model_vars[is_match_var_name] = is_match = utils.ortools_expression_to_bool_var(
                    ctx.model, is_match_var_name,
                    actual_n_matched == target_n_matched,
                    actual_n_matched != target_n_matched
                )

                # Add the objective
                weight = preference.weight
                ctx.objective += weight * is_match
                ctx.reports.append(Report(unique_var_prefix, is_match, lambda x: x != target_n_matched))

PREFERENCE_TYPES_TO_FUNC = {
    "shift type requirement": shift_type_requirements,
    "all people work at most one shift per day": all_people_work_at_most_one_shift_per_day,
    "assign shifts evenly": assign_shifts_evenly,
    "shift request": shift_request,
    "unwanted shift type successions": unwanted_shift_type_successions,
}
