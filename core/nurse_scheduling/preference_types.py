"""Preference handlers that build scheduling constraints and objectives."""

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
import math

from . import constants, models, utils
from .context import Context
from .report import Report

logger = logging.getLogger(__name__)

# Input parsing and selector expansion belong to the Pydantic compiler. Keep
# runtime preference handlers focused on solver construction.


def shift_type_requirements(
    ctx: Context,
    preference: models.ShiftTypeRequirementsPreference,
    compiled_preference: models.CompiledShiftTypeRequirements,
    preference_idx,
):
    # Hard constraint
    # For all requirement groups, the required number of people must be
    # fulfilled. Note that a concrete shift is represented as (d, s).
    #
    # A shiftType list applies one requirement per top-level selector:
    #   shiftType: [D, E], requiredNumPeople: 1
    #   sum_p shifts[(d, D, p)] == 1
    #   sum_p shifts[(d, E, p)] == 1
    #
    # A group selector or nested shiftType list creates an aggregate staffing
    # equation within that top-level selector:
    #   shiftType: [DayOrEvening], where DayOrEvening = [D, E]
    #   sum_{s in [D,E], p}(shifts[(d, s, p)]) == 1
    #
    #   shiftType: [[D, E]], requiredNumPeople: 1
    #   sum_{s in [D,E], p}(shifts[(d, s, p)]) == 1
    #
    # A concrete (date, shift type) may appear in more than one requirement
    # equation, including aggregate groups. This can intentionally layer
    # aggregate and concrete staffing requirements.
    #
    # Also note that this requirement is used in other preference types,
    # so this could not be implemented as a special case of shift_count.

    coefficients = dict(compiled_preference.coefficients)
    for d in compiled_preference.dates:
        for group_idx, ss in enumerate(compiled_preference.shift_type_groups):
            for s in ss:
                # A requirement expands through date and shift type groups into
                # concrete (date, shift type) pairs. Duplicates are allowed
                # because all matching constraints are applied.
                coverage_key = (d, s)
                if coverage_key in ctx.shift_type_requirement_coverage:
                    previous_preference_idx = ctx.shift_type_requirement_coverage[coverage_key]
                    date_id = str(ctx.dates.items[d])
                    shift_type_id = ctx.shiftTypes.items[s].id
                    logger.info(
                        "Duplicate shift type requirement coverage for "
                        f"date '{date_id}' and shift type '{shift_type_id}' "
                        f"in preferences {previous_preference_idx} and {preference_idx}; "
                        "applying all matching requirements."
                    )
                else:
                    ctx.shift_type_requirement_coverage[coverage_key] = preference_idx

            # Get the set of people who can work each shift type in this
            # requirement group. Without explicit qualifiedPeople, eligibility
            # can differ by concrete shift type.
            qualified_ps_by_s = {s: ctx.map_ds_p[(d, s)] for s in ss}
            if compiled_preference.qualified_people is not None:
                # If qualifiedPeople is specified, only allow those people to
                # work any shift type in the group.
                qualified_ps = compiled_preference.qualified_people
                qualified_ps_by_s = {s: qualified_ps for s in ss}
                for s in ss:
                    unqualified_n_people = sum(
                        ctx.shifts[(d, s, p)] for p in range(ctx.n_people) if p not in qualified_ps
                    )
                    ctx.solver.add_constraint(unqualified_n_people == 0)

            # Add the hard lower/exact staffing constraint over the whole
            # requirement group. For singleton groups this is the simple
            # per-shift constraint; for aggregate groups this sums across all
            # shift types in the group.
            actual_n_people = sum(coefficients[s] * ctx.shifts[(d, s, p)] for s in ss for p in qualified_ps_by_s[s])
            if preference.preferredNumPeople is not None:
                ctx.solver.add_constraint(actual_n_people >= preference.requiredNumPeople)
            else:
                ctx.solver.add_constraint(actual_n_people == preference.requiredNumPeople)

            # Add soft constraint for preferred number of people if specified
            if preference.preferredNumPeople is not None:
                ctx.solver.add_constraint(actual_n_people <= preference.preferredNumPeople)
                # Create a variable to track the difference between actual and preferred number of people
                diff_var_name = f"pref_{preference_idx}_d_{d}_g_{group_idx}_diff"
                ctx.model_vars[diff_var_name] = diff = ctx.solver.new_int_var(
                    0, preference.preferredNumPeople, diff_var_name
                )
                ctx.solver.add_constraint(diff == preference.preferredNumPeople - actual_n_people)

                # Add the objective
                weight = preference.weight
                utils.add_objective(ctx, weight, diff)
                ctx.reports.append(Report(f"shift_type_requirements_{diff_var_name}", diff, lambda x: x == 0))


def all_people_work_at_most_one_shift_per_day(ctx: Context, preference, compiled_preference, preference_idx):
    # Hard constraint
    # For all people, for all days, only work at most one shift.
    # Note that a shift in day `d` can be represented as `s` instead of (d, s).
    # i.e., sum_{s}(shifts[(d, s, p)]) <= 1, for all (d, p)
    #
    # This constraint is encoded while creating off variables:
    #   offs[(d, p)] + sum_{s}(shifts[(d, s, p)]) == 1
    pass


def shift_request(
    ctx: Context,
    preference: models.ShiftRequestPreference,
    compiled_preference: models.CompiledShiftRequest,
    preference_idx,
):
    # Soft constraint
    # For all people, try to fulfill the shift requests.
    # Note that a shift is represented as (d, s)
    # i.e., max(weight * shifts[(d, s, p)]), for all satisfying (d, s)
    for d in compiled_preference.dates:
        # Note that the order of p and s is inverted deliberately
        for p in compiled_preference.people:
            weight = preference.weight
            if utils.is_ss_equivalent_to_all(compiled_preference.shift_types, ctx.n_shift_types):
                # Add the objective
                utils.add_objective(ctx, weight, ctx.solver.negate(ctx.offs[(d, p)]))
                ctx.reports.append(
                    Report(f"shift_request_pref_{preference_idx}_d_{d}_p_{p}_offs", ctx.offs[(d, p)], lambda x: x == 0)
                )
            else:
                for s in compiled_preference.shift_types:
                    # Add the objective
                    if s == constants.OFF_sid:
                        utils.add_objective(ctx, weight, ctx.offs[(d, p)])
                        ctx.reports.append(
                            Report(
                                f"shift_request_pref_{preference_idx}_d_{d}_p_{p}_offs",
                                ctx.offs[(d, p)],
                                lambda x: x == 1,
                            )
                        )
                    else:
                        utils.add_objective(ctx, weight, ctx.shifts[(d, s, p)])
                        ctx.reports.append(
                            Report(
                                f"shift_request_pref_{preference_idx}_d_{d}_s_{s}_p_{p}_shifts",
                                ctx.shifts[(d, s, p)],
                                lambda x: x == 1,
                            )
                        )


def shift_type_successions(
    ctx: Context,
    preference: models.ShiftTypeSuccessionsPreference,
    compiled_preference: models.CompiledShiftTypeSuccessions,
    preference_idx,
):
    # Soft constraint
    # For all people, for all start date, try to match the shift type successions.
    # Note that a shift is represented as (d, s)
    # i.e., max(weight * (actual_n_matched == target_n_matched)), for all p,
    # where actual_n_matched = sum_{(d, s)}(shifts[(d, s, p)]), for all satisfying (d, s)
    def _pattern_element_match_expr(d, p, pattern_element):
        if pattern_element.matches_all_working_shifts:
            return ctx.solver.negate(ctx.offs[(d, p)]), True
        matches = [
            ctx.shifts[(d, s, p)] if s != constants.OFF_sid else ctx.offs[(d, p)] for s in pattern_element.shift_types
        ]
        if len(matches) == 1:
            return matches[0], True
        return sum(matches), False

    # Resolve the Pydantic private attribute once because this hot loop runs
    # for every selected person and pattern start date.
    histories = ctx.compiled_schedule.histories
    for p in compiled_preference.people:
        history = histories[p]
        for d_begin in range(ctx.n_days - len(compiled_preference.pattern) + 1):
            # Check if all dates in the pattern range are valid
            if not all(
                d in compiled_preference.date_set for d in range(d_begin, d_begin + len(compiled_preference.pattern))
            ):
                continue
            # Match all patterns that start at day d_begin
            patterns = [compiled_preference.pattern]
            # Consider history data to check for patterns that start at day 0
            # We only need to check day 0 since any pattern that matches history must include it
            if d_begin == 0 and history is not None:
                # For each pattern, check if its prefix matches the end of shift history
                # If so, add the remaining suffix as a new pattern to check
                for history_suffix_len in range(1, min(len(compiled_preference.pattern), len(history)) + 1):
                    history_suffix = history[-history_suffix_len:]
                    pattern_prefix = compiled_preference.pattern[:history_suffix_len]
                    if all(history_suffix[i] in pattern_prefix[i].shift_types for i in range(history_suffix_len)):
                        # If history suffix matches pattern prefix, add remaining pattern suffix as new pattern
                        # This is equivalent to checking patterns that span across history and future days
                        patterns.append(compiled_preference.pattern[history_suffix_len:])
            for pattern_idx, pattern in enumerate(patterns):
                target_n_matched = len(pattern)
                unique_var_prefix = (
                    f"shift_type_successions_pref_{preference_idx}_p_{p}_dbegin_{d_begin}_pattern_{pattern_idx}"
                )
                if target_n_matched == 0:
                    # History already completes this pattern before the first schedulable day.
                    is_match_var_name = f"{unique_var_prefix}_is_match"
                    ctx.model_vars[is_match_var_name] = is_match = ctx.solver.new_bool_var(is_match_var_name)
                    ctx.solver.add_constraint(is_match == 1)
                    utils.add_objective(ctx, preference.weight, is_match)
                    ctx.reports.append(Report(unique_var_prefix, is_match, lambda x: x == 1))
                    continue

                pattern_element_matches = [
                    _pattern_element_match_expr(d_begin + i, p, pattern[i]) for i in range(target_n_matched)
                ]
                actual_n_matched = sum(match_expr for match_expr, _is_literal in pattern_element_matches)
                weight = preference.weight

                if weight == -math.inf:
                    ctx.solver.add_constraint(actual_n_matched <= target_n_matched - 1)
                    continue
                if weight == math.inf:
                    ctx.solver.add_constraint(actual_n_matched == target_n_matched)
                    continue

                # Construct: is_match = all pattern elements match.
                is_match_var_name = f"{unique_var_prefix}_is_match"
                is_literal_pattern = all(is_literal for _match_expr, is_literal in pattern_element_matches)
                if weight < 0 and is_literal_pattern:
                    # For negative soft successions, is_match only needs to
                    # mark a violation. If every literal matches, the right
                    # side becomes 1 and forces is_match to 1. Otherwise, the
                    # constraint allows is_match to remain 0, and the negative
                    # objective weight makes 0 strictly preferred.
                    ctx.model_vars[is_match_var_name] = is_match = ctx.solver.new_bool_var(is_match_var_name)
                    ctx.solver.add_constraint(is_match >= actual_n_matched - target_n_matched + 1)
                    utils.add_objective(ctx, weight, is_match)
                    ctx.reports.append(Report(unique_var_prefix, is_match, lambda x: x == 0))
                    continue
                if is_literal_pattern and ctx.solver.should_use_bool_and_var(len(pattern_element_matches)):
                    ctx.model_vars[is_match_var_name] = is_match = ctx.solver.create_bool_and_var(
                        is_match_var_name,
                        [match_expr for match_expr, _is_literal in pattern_element_matches],
                    )
                else:
                    ctx.model_vars[is_match_var_name] = is_match = ctx.solver.create_bool_var_with_constraint(
                        is_match_var_name,
                        actual_n_matched,
                        constants.Operator.EQ,
                        target_n_matched,
                        (0, target_n_matched),
                    )

                utils.add_objective(ctx, weight, is_match)
                ctx.reports.append(Report(unique_var_prefix, is_match, lambda x: x == 1))


def shift_count(
    ctx: Context,
    preference: models.ShiftCountPreference,
    compiled_preference: models.CompiledShiftCount,
    preference_idx,
):
    # Soft constraint
    # For specified people, dates, and shift types, penalize violations of the expression
    # The expression is evaluated as a mathematical formula where x is the actual evaluated value
    # and T is the target value
    coefficients = dict(compiled_preference.coefficients)
    weight = preference.weight
    for expression, T in zip(compiled_preference.expressions, compiled_preference.targets, strict=True):
        for p in compiled_preference.people:
            unique_var_prefix = f"pref_{preference_idx}_p_{p}"
            # Calculate actual number of shifts for this person
            x = sum(
                coefficients[s] * (ctx.shifts[(d, s, p)] if s != constants.OFF_sid else ctx.offs[(d, p)])
                for d in compiled_preference.dates
                for s in compiled_preference.shift_types
            )

            # TODO: Also Report value of `x`

            # Each person can work at most one selected shift per day.
            max_x = len(compiled_preference.dates) * max(coefficients.values())

            # Evaluate the expression
            if expression == "|x - T|^2":
                # Note that a shift is represented as (d, s)
                # i.e., min(weight * (actual_n_shifts - T) ** 2), for all p,
                # where actual_n_shifts = sum_{(d, s)}(shifts[(d, s, p)])
                # Create a variable to represent the deviation from target
                # - x in [0, max_x]
                # - x - T in [0 - T, max_x - T]
                # - abs(x - T) in [0, max(|0 - T|, |max_x - T|)]
                max_abs_diff = max(abs(0 - T), abs(max_x - T))
                abs_diff_var_name = f"{unique_var_prefix}_abs_diff"
                ctx.model_vars[abs_diff_var_name] = abs_diff = ctx.solver.new_int_var(
                    0,
                    max_abs_diff,
                    abs_diff_var_name,
                )  # Min is 0, since abs_diff is assigned through abs
                # Use abstracted abs equality method
                ctx.solver.add_abs_equality(abs_diff, x - T, (0 - T, max_x - T))
                # Square the difference
                squared_var_name = f"{unique_var_prefix}_squared"
                ctx.model_vars[squared_var_name] = squared = ctx.solver.new_int_var(
                    0, max_abs_diff**2, squared_var_name
                )
                # Use abstracted squared equality method
                ctx.solver.add_squared_equality(squared, abs_diff, (0, max_abs_diff))
                # Add the objective
                utils.add_objective(ctx, weight, squared)
                ctx.reports.append(Report(f"shift_count_{squared_var_name}", squared, lambda x: x == 0))
            else:
                expr_var_name = f"{unique_var_prefix}_expr"
                operators = {
                    "x >= T": constants.Operator.GE,
                    "x <= T": constants.Operator.LE,
                    "x > T": constants.Operator.GT,
                    "x < T": constants.Operator.LT,
                    "x = T": constants.Operator.EQ,
                }
                # Add the objective
                ctx.model_vars[expr_var_name] = expr = ctx.solver.create_bool_var_with_constraint(
                    expr_var_name,
                    x,
                    operators[expression],
                    T,
                    (0, max_x),
                )
                utils.add_objective(ctx, weight, expr)
                # TODO: Be aware of signs of `weight`?
                ctx.reports.append(Report(f"shift_count_{unique_var_prefix}_expr", expr, lambda x: x))


def shift_affinity(
    ctx: Context,
    preference: models.ShiftAffinityPreference,
    compiled_preference: models.CompiledShiftAffinity,
    preference_idx,
):
    # Soft constraint
    # For specified date, people1, people2, and shift types, encourage or discourage working together.
    # Positive weight encourages affinity (working together), negative weight encourages repulsion (working apart)
    # By unpacking the nested lists, for all `p1s` in `people1`,
    # `p2s` in `people2`, and `ss` in `shiftTypes`,
    # the preference is satisfied on the date if at least one member of `p1s` and
    # at least one member of `p2s` are assigned to one of the specified shift types `ss`,
    # which doesn't necessarily need to be the same shift type. i.e.,
    # max(weight * (some_p1s_matched_some_ss and some_p2s_matched_some_ss)), for all `p1s` in `people1`, `p2s` in `people2`, and `ss` in `shiftTypes`

    # Example scenarios (formulation rationale):
    # - `p1s` represents a student who should work with at least one teacher in `p2s`,
    #   without needing additional incentive to work with more than one teacher.
    # - Some members of `p1s` and `p2s` prefer not to work together,
    #   while there are multiple shift types that have overlapping time.

    # Other considerations:
    # - If `p1s` wants to work with multiple `p2s` simultaneously,
    #   this can be modeled using multiple shift affinity preferences,
    #   or the nested `people2` list.
    # - If `p1s` wants to work with `p2s` on multiple shift types (with non-overlapping time),
    #   this can also be handled with multiple shift affinity preferences,
    #   or the nested `shiftTypes` list.
    #
    # If the shift affinity preference is defined to act on each pair of people1 and people2,
    # or people1 and people2 must both work on the exact same shift type,
    # we will lose the ability to handle the example scenarios above.
    # Therefore, the current formulation is the most flexible one, albeit a bit confusing on first sight.

    for d in compiled_preference.dates:
        for i, p1s in enumerate(compiled_preference.people1_groups):
            for j, p2s in enumerate(compiled_preference.people2_groups):
                for k, ss in enumerate(compiled_preference.shift_type_groups):
                    unique_var_prefix = f"pref_{preference_idx}_d_{d}_i_{i}_j_{j}_k_{k}"
                    some_p1_matched_var_name = f"{unique_var_prefix}_some_p1_matched"
                    some_p2_matched_var_name = f"{unique_var_prefix}_some_p2_matched"
                    is_match_var_name = f"{unique_var_prefix}_is_match"
                    sum1 = sum(
                        ctx.shifts[(d, s, p)] if s != constants.OFF_sid else ctx.offs[(d, p)] for p in p1s for s in ss
                    )
                    ctx.model_vars[some_p1_matched_var_name] = some_p1_matched = (
                        ctx.solver.create_bool_var_with_constraint(
                            some_p1_matched_var_name,
                            sum1,
                            constants.Operator.GE,
                            1,
                            (0, len(p1s) * len(ss)),
                        )
                    )
                    sum2 = sum(
                        ctx.shifts[(d, s, p)] if s != constants.OFF_sid else ctx.offs[(d, p)] for p in p2s for s in ss
                    )
                    ctx.model_vars[some_p2_matched_var_name] = some_p2_matched = (
                        ctx.solver.create_bool_var_with_constraint(
                            some_p2_matched_var_name,
                            sum2,
                            constants.Operator.GE,
                            1,
                            (0, len(p2s) * len(ss)),
                        )
                    )
                    sum3 = some_p1_matched + some_p2_matched
                    ctx.model_vars[is_match_var_name] = is_match = ctx.solver.create_bool_var_with_constraint(
                        is_match_var_name,
                        sum3,
                        constants.Operator.EQ,
                        2,
                        (0, 2),
                    )
                    weight = preference.weight
                    utils.add_objective(ctx, weight, is_match)
                    ctx.reports.append(
                        Report(f"shift_affinity_{unique_var_prefix}_is_match", is_match, lambda x: x == 1)
                    )


PREFERENCE_TYPES_TO_FUNC = {
    models.SHIFT_TYPE_REQUIREMENT: shift_type_requirements,
    models.AT_MOST_ONE_SHIFT_PER_DAY: all_people_work_at_most_one_shift_per_day,
    models.SHIFT_REQUEST: shift_request,
    models.SHIFT_TYPE_SUCCESSIONS: shift_type_successions,
    models.SHIFT_COUNT: shift_count,
    models.SHIFT_AFFINITY: shift_affinity,
}
