import itertools
import math
from . import utils
from .context import Context
from .report import Report
from . import models

# Leave most parsing to the caller, keep the function here simple.

def shift_type_requirements(ctx: Context, preference, preference_idx):
    # Hard constraint
    # For all shift types, the requirements (# of people) must be fulfilled.
    # Note that a shift is represented as (d, s)
    # i.e., sum_{p}(shifts[(d, s, p)]) == required_num_people, for all (d, s)
    # Also note that this requirement is used in other preference types,
    # so this could not be implemented as a special case of shift_count.

    # TODO: Check if each (d, s) is specified by only one shift type requirement
    
    ds = range(ctx.n_days)
    if preference.date is not None:
        ds = utils.parse_dates(preference.date, ctx.startdate, ctx.enddate, ctx.country)
    ss = utils.parse_sids(preference.shift_type, ctx.map_sid_s)
    if len(ss) == 0:
        raise ValueError(f"Non-empty shift types are required, but got {preference.shift_type}")
    for d in ds:
        for s in ss:
            # Get the set of people who can work this shift
            qualified_ps = ctx.map_ds_p[(d, s)]
            if preference.qualified_people is not None:
                # If qualified_people is specified, only allow those people to work the shift
                qualified_ps = utils.parse_pids(preference.qualified_people, ctx.map_pid_p)
                unqualified_n_people = sum(ctx.shifts[(d, s, p)] for p in range(ctx.n_people) if p not in qualified_ps)
                ctx.model.Add(unqualified_n_people == 0)
            
            # Add constraint that exactly required_num_people must be assigned from the qualified people
            actual_n_people = sum(ctx.shifts[(d, s, p)] for p in qualified_ps)
            if preference.preferred_num_people is not None:
                ctx.model.Add(actual_n_people >= preference.required_num_people)
            else:
                ctx.model.Add(actual_n_people == preference.required_num_people)

            # Add soft constraint for preferred number of people if specified
            if preference.preferred_num_people is not None:
                ctx.model.Add(actual_n_people <= preference.preferred_num_people)
                # Create a variable to track the difference between actual and preferred number of people
                diff_var_name = f"pref_{preference_idx}_d_{d}_s_{s}_diff"
                ctx.model_vars[diff_var_name] = diff = ctx.model.NewIntVar(0, preference.preferred_num_people, diff_var_name)
                ctx.model.Add(diff == preference.preferred_num_people - actual_n_people)
                
                # Add the objective
                weight = preference.weight
                if weight in [utils.INF, utils.NINF]:
                    raise ValueError(f"'INF' and '-INF' weights are not allowed for {models.SHIFT_TYPE_REQUIREMENT} with 'preferred_num_people'. Use 'required_num_people' instead to enforce hard constraints.")
                utils.add_objective(ctx, weight, diff)
                ctx.reports.append(Report(f"shift_type_requirements_{diff_var_name}", diff, lambda x: x == 0))

def all_people_work_at_most_one_shift_per_day(ctx: Context, preference, preference_idx):
    # Hard constraint
    # For all people, for all days, only work at most one shift.
    # Note that a shift in day `d` can be represented as `s` instead of (d, s).
    # i.e., sum_{s}(shifts[(d, s, p)]) <= 1, for all (d, p)
    for (d, p), ss in ctx.map_dp_s.items():
        actual_n_shifts = sum(ctx.shifts[(d, s, p)] for s in ss)
        maximum_n_shifts = 1
        ctx.model.Add(actual_n_shifts <= maximum_n_shifts)

def shift_request(ctx: Context, preference, preference_idx):
    # Soft constraint
    # For all people, try to fulfill the shift requests.
    # Note that a shift is represented as (d, s)
    # i.e., max(weight * shifts[(d, s, p)]), for all satisfying (d, s)
    ds = utils.parse_dates(preference.date, ctx.startdate, ctx.enddate, ctx.country)
    ss = utils.parse_sids(preference.shift_type, ctx.map_sid_s)
    ps = utils.parse_pids(preference.person, ctx.map_pid_p)
    for d in ds:
        # Note that the order of p and s is inverted deliberately
        for p in ps:
            weight = preference.weight
            if preference.shift_type == utils.ALL:
                assert utils.is_ss_equivalent_to_all(ss, ctx.n_shift_types)
                # Add the objective
                utils.add_objective(ctx, weight, ctx.offs[(d, p)].Not())
                ctx.reports.append(Report(f"shift_request_pref_{preference_idx}_d_{d}_p_{p}_offs", ctx.offs[(d, p)], lambda x: x == 0))
            else:
                if utils.is_ss_equivalent_to_all(ss, ctx.n_shift_types):
                    raise ValueError(f"Shift type should be 'ALL', but got {preference.shift_type} instead")
                for s in ss:
                    # Add the objective
                    if s == utils.OFF_sid:
                        utils.add_objective(ctx, weight, ctx.offs[(d, p)])
                        ctx.reports.append(Report(f"shift_request_pref_{preference_idx}_d_{d}_p_{p}_offs", ctx.offs[(d, p)], lambda x: x == 1))
                    else:
                        utils.add_objective(ctx, weight, ctx.shifts[(d, s, p)])
                        ctx.reports.append(Report(f"shift_request_pref_{preference_idx}_d_{d}_s_{s}_p_{p}_shifts", ctx.shifts[(d, s, p)], lambda x: x == 1))

def shift_type_successions(ctx: Context, preference, preference_idx):
    # Soft constraint
    # For all people, for all start date, try to match the shift type successions.
    # Note that a shift is represented as (d, s)
    # i.e., max(weight * (actual_n_matched == target_n_matched)), for all p,
    # where actual_n_matched = sum_{(d, s)}(shifts[(d, s, p)]), for all satisfying (d, s)
    ps = utils.parse_pids(preference.person, ctx.map_pid_p)
    if not isinstance(preference.pattern, list):
        raise ValueError(f"Pattern must be a list, but got {type(preference.pattern)}")
    # Convert each pattern element to a list and parse shift IDs
    flattened_pattern = [
        sorted(set(itertools.chain.from_iterable(
            utils.parse_sids(sid, ctx.map_sid_s)
            for sid in (element if isinstance(element, list) else [element])
        )))
        for element in preference.pattern
    ]
    parsed_pattern = []
    for i in range(len(flattened_pattern)):
        if preference.pattern[i] == utils.ALL:
            parsed_pattern.append(utils.ALL)
        elif utils.is_ss_equivalent_to_all(flattened_pattern[i], ctx.n_shift_types):
            raise ValueError(f"Pattern must not include 'ALL', but got {flattened_pattern[i]}")
        else:
            parsed_pattern.append(flattened_pattern[i])
    assert len(parsed_pattern) == len(flattened_pattern)

    for p in ps:
        for d_begin in range(ctx.n_days - len(flattened_pattern) + 1):
            # Match all patterns that start at day d_begin
            patterns = [parsed_pattern]
            # Consider history data to check for patterns that start at day 0
            # We only need to check day 0 since any pattern that matches history must include it
            if d_begin == 0 and ctx.people[p].history is not None:
                history = [utils.parse_sids(sid, ctx.map_sid_s) for sid in ctx.people[p].history]
                for i in range(len(history)):
                    if len(history[i]) != 1 and ctx.people[p].history[i] != utils.OFF:
                        raise ValueError(f"History must not include nested ID, but got {ctx.people[p].history[i]}")
                    if ctx.people[p].history[i] == utils.ALL:
                        raise ValueError(f"History must not include 'ALL', but got {ctx.people[p].history[i]}")
                    else:
                        history[i] = history[i][0]
                # For each pattern, check if its prefix matches the end of shift history
                # If so, add the remaining suffix as a new pattern to check
                for history_suffix_len in range(1, min(len(flattened_pattern), len(history)) + 1):
                    history_suffix = history[-history_suffix_len:]
                    pattern_prefix = flattened_pattern[:history_suffix_len]
                    if all(history_suffix[i] in pattern_prefix[i] for i in range(history_suffix_len)):
                        # If history suffix matches pattern prefix, add remaining pattern suffix as new pattern
                        # This is equivalent to checking patterns that span across history and future days
                        patterns.append(parsed_pattern[history_suffix_len:])
            for pattern in patterns:
                # For each day and pattern, collect all matched shifts
                match_shifts_in_day = []
                for i in range(len(pattern)):
                    if pattern[i] == utils.ALL:
                        match_shifts_in_day.append([ctx.offs[(d_begin+i, p)].Not()])
                    else:
                        match_shifts_in_day.append([ctx.shifts[(d_begin+i, s, p)] if s != utils.OFF_sid else ctx.offs[(d_begin+i, p)] for s in pattern[i]])
                target_n_matched = len(pattern)
                for idx, seq in enumerate(itertools.product(*match_shifts_in_day)):
                    assert len(seq) == len(pattern)
                    # Construct: is_match = (actual_n_matched == target_n_matched)
                    unique_var_prefix = f"shift_type_successions_pref_{preference_idx}_p_{p}_dbegin_{d_begin}_seq_{idx}"
                    is_match_var_name = f"{unique_var_prefix}_is_match"
                    actual_n_matched = sum(seq)
                    ctx.model_vars[is_match_var_name] = is_match = utils.ortools_expression_to_bool_var(
                        ctx.model, is_match_var_name,
                        actual_n_matched == target_n_matched,
                        actual_n_matched != target_n_matched
                    )

                    # Add the objective
                    weight = preference.weight
                    utils.add_objective(ctx, weight, is_match)
                    ctx.reports.append(Report(unique_var_prefix, is_match, lambda x: x != target_n_matched))

def shift_count(ctx: Context, preference, preference_idx):
    # Soft constraint
    # For specified people, dates, and shift types, penalize violations of the expression
    # The expression is evaluated as a mathematical formula where x is the actual evaluated value
    # and T is the target value (can be a constant or special constant names)
    ps = utils.parse_pids(preference.person, ctx.map_pid_p)
    c_ds = utils.parse_dates(preference.count_dates, ctx.startdate, ctx.enddate, ctx.country)
    c_ss = utils.parse_sids(preference.count_shift_types, ctx.map_sid_s)

    # Calculate total preferred shifts across all shift type requirements
    total_shifts = 0
    for pref in ctx.preferences:
        if pref.type == models.SHIFT_TYPE_REQUIREMENT:
            shift_types = utils.parse_sids(pref.shift_type, ctx.map_sid_s)
            total_shifts += (pref.preferred_num_people or pref.required_num_people) * len(shift_types) * ctx.n_days

    if len(preference.expression) == 0:
        raise ValueError(f"Expression must not be empty")
    if isinstance(preference.expression, list) and isinstance(preference.expression[0], tuple):
        # Check each expression has length 2
        for expr in preference.expression:
            if len(expr) != 2:
                raise ValueError(f"Each expression must be a tuple of length 2, but got {expr}")
        # Is nested expression
        expressions, targets = zip(*preference.expression)
    elif isinstance(preference.expression, tuple):
        # Is single expression
        if len(preference.expression) != 2:
            raise ValueError(f"Expression must be a single tuple, but got {preference.expression}")
        expressions = [preference.expression[0]]
        targets = [preference.expression[1]]
    else:
        raise ValueError(f"Expression must be a list of tuples or a single tuple, but got {type(preference.expression)}")
    weight = preference.weight
    for i in range(len(expressions)):
        expression, target = expressions[i], targets[i]
        if isinstance(target, int):
            T = target
            if T < 0:
                raise ValueError(f"Target must be non-negative, but got {T}")
        elif target == 'floor(AVG_SHIFTS_PER_PERSON)':
            T = math.floor(total_shifts / ctx.n_people)
        elif target == 'ceil(AVG_SHIFTS_PER_PERSON)':
            T = math.ceil(total_shifts / ctx.n_people)
        elif target == 'round(AVG_SHIFTS_PER_PERSON)':
            # Keep in mind the rounding behavior of Python
            # Ref: https://stackoverflow.com/q/10825926
            T = round(total_shifts / ctx.n_people)
        else:
            raise ValueError(f"Unsupported target: {target}")
        assert isinstance(T, int)

        for p in ps:
            unique_var_prefix = f"pref_{preference_idx}_p_{p}"
            # Calculate actual number of shifts for this person
            if preference.count_shift_types == utils.ALL:
                assert utils.is_ss_equivalent_to_all(c_ss, ctx.n_shift_types)
                x = sum(ctx.shifts[(d, s, p)] for d in c_ds for s in c_ss)
            else:
                if utils.is_ss_equivalent_to_all(c_ss, ctx.n_shift_types):
                    raise ValueError(f"Shift type should be 'ALL', but got {preference.count_shift_types} instead")
                x = sum(ctx.shifts[(d, s, p)] if s != utils.OFF_sid else ctx.offs[(d, p)] for d in c_ds for s in c_ss)

            # TODO: Also Report value of `x`
            
            SUPPORTED_EXPRESSIONS = ['|x - T|^2', 'x >= T', 'x <= T', 'x > T', 'x < T']
            # Evaluate the expression
            if expression == '|x - T|^2':
                # Note that a shift is represented as (d, s)
                # i.e., min(weight * (actual_n_shifts - T) ** 2), for all p,
                # where actual_n_shifts = sum_{(d, s)}(shifts[(d, s, p)])
                # Create a variable to represent the deviation from target
                MAX = max(total_shifts - T, T)
                diff_var_name = f"{unique_var_prefix}_diff"
                ctx.model_vars[diff_var_name] = diff = ctx.model.NewIntVar(0, MAX, diff_var_name) # Min is 0, since diff is assigned through AddAbsEquality
                ctx.model.AddAbsEquality(diff, x - T)
                # Square the difference
                squared_var_name = f"{unique_var_prefix}_squared"
                ctx.model_vars[squared_var_name] = squared = ctx.model.NewIntVar(0, MAX**2, squared_var_name)
                ctx.model.AddMultiplicationEquality(squared, diff, diff)
                # Add the objective
                if weight == utils.INF:
                    raise ValueError(f"'INF' weights are not allowed for shift count with '{expression}'.")
                elif weight != utils.NINF and weight > 0:
                    # -INF means x == T, which is okay
                    raise ValueError(f"Weight must be non-positive for shift count with '{expression}'.")
                utils.add_objective(ctx, weight, squared)
                ctx.reports.append(Report(f"shift_count_{squared_var_name}", squared, lambda x: x == 0))
            elif expression in SUPPORTED_EXPRESSIONS:
                expr_var_name = f"{unique_var_prefix}_expr"
                # str -> (expr, expr.Not())
                equations = {
                    'x >= T': (x >= T, x < T),
                    'x <= T': (x <= T, x > T),
                    'x > T': (x > T, x <= T),
                    'x < T': (x < T, x >= T),
                }[expression]
                # Add the objective
                ctx.model_vars[expr_var_name] = expr = utils.ortools_expression_to_bool_var(
                    ctx.model, expr_var_name,
                    equations[0],
                    equations[1]
                )
                utils.add_objective(ctx, weight, expr)
                # TODO: Be aware of signs of `weight`?
                ctx.reports.append(Report(f"shift_count_{unique_var_prefix}_expr", expr, lambda x: x))
            else:
                raise ValueError(f"Unsupported expression: {expression}. Supported expressions are: {SUPPORTED_EXPRESSIONS}")

PREFERENCE_TYPES_TO_FUNC = {
    models.SHIFT_TYPE_REQUIREMENT: shift_type_requirements,
    models.AT_MOST_ONE_SHIFT_PER_DAY: all_people_work_at_most_one_shift_per_day,
    models.SHIFT_REQUEST: shift_request,
    models.SHIFT_TYPE_SUCCESSIONS: shift_type_successions,
    models.SHIFT_COUNT: shift_count,
}
