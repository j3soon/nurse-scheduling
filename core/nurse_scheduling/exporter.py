import pandas as pd
from ortools.sat.python import cp_model

from .context import Context
from . import utils, models, constants


def get_people_versus_date_dataframe(ctx: Context, solver: cp_model.CpSolver, prettify: bool = False):
    # Initialize dataframe with size including leading rows and columns
    n_leading_rows, n_leading_cols = 2, 1
    n_trailing_rows, n_trailing_cols = 2, 0
    
    # Add extra columns and rows for prettify mode
    extra_cols = 2 if prettify else 0  # Empty column + OFF count column
    extra_rows = (1 + ctx.n_shift_types) if prettify else 0  # Empty row + one row per shift type
    
    df = pd.DataFrame(
        "",
        index=range(n_leading_rows + len(ctx.people.items) + n_trailing_rows + extra_rows),
        columns=range(n_leading_cols + len(ctx.dates.items) + n_trailing_cols + extra_cols)
    )

    # Fill day numbers and weekdays
    # - row 0 contains day number
    # - row 1 contains weekday
    for d, date in enumerate(ctx.dates.items):
        if ctx.dates.items[0].year != ctx.dates.items[-1].year:
            df.iloc[0, n_leading_cols + d] = date.strftime('%Y/%-m/%-d')
        elif ctx.dates.items[0].month != ctx.dates.items[-1].month:
            df.iloc[0, n_leading_cols + d] = date.strftime('%-m/%-d')
        else:
            df.iloc[0, n_leading_cols + d] = date.day
        df.iloc[1, n_leading_cols + d] = date.strftime('%a')

    # Fill person descriptions
    # - column 0 contains person description
    for p, person in enumerate(ctx.people.items):
        df.iloc[n_leading_rows+p, 0] = person.id

    # Set cell values based on solver results
    for (d, p) in ctx.map_dp_s.keys():
        assert df.iloc[n_leading_rows+p, n_leading_cols+d] == ""
        cell_value = ""
        for s in ctx.map_dp_s[(d, p)]:
            if solver.Value(ctx.shifts[(d, s, p)]) == 1:
                if cell_value != "":
                    cell_value += ", "
                cell_value += ctx.shiftTypes.items[s].id
        if prettify:
            # Only consider single-person, single-shift-type, list-of-single-date style shift request
            # Add a ` [OFF]` suffix if the person requests OFF
            # Add a ` [X]` suffix if the shift request is violated
            for pref in ctx.preferences:
                if pref.type != models.SHIFT_REQUEST:
                    continue
                if pref.weight == 0:
                    continue
                ds = utils.parse_dates(pref.date, ctx.map_did_d, ctx.dates.range)
                ss = utils.parse_sids(pref.shiftType, ctx.map_sid_s)
                ps = utils.parse_pids(pref.person, ctx.map_pid_p)
                if len(ss) != 1 or len(ps) != 1:
                    # Skip since is not single person and single shift type style
                    continue
                if len(ds) != len(pref.date):
                    # Skip since only count for single-date style
                    continue
                if d not in ds or p not in ps:
                    continue
                target_value = 1 if pref.weight > 0 else 0
                for s in ss:
                    var = ctx.shifts[(d, s, p)] if s != constants.OFF_sid else ctx.offs[(d, p)]
                    if s == constants.OFF_sid:
                        cell_value += " [OFF]"
                    if solver.Value(var) != target_value:
                        cell_value += " [X]"
        df.iloc[n_leading_rows+p, n_leading_cols+d] = cell_value

    # Fill objective value
    df.iloc[n_leading_rows + len(ctx.people.items), 0] = "Score"
    df.iloc[n_leading_rows + len(ctx.people.items), 1] = solver.Value(ctx.objective) # or solver.ObjectiveValue()
    # Fill solver status
    df.iloc[n_leading_rows + len(ctx.people.items) + 1, 0] = "Status"
    df.iloc[n_leading_rows + len(ctx.people.items) + 1, 1] = ctx.solver_status

    # Sanity check with offs variables
    if not prettify:
        for (d, p) in ctx.offs.keys():
            if solver.Value(ctx.offs[(d, p)]) == 1:
                assert df.iloc[n_leading_rows+p, n_leading_cols+d] == ""
            else:
                assert df.iloc[n_leading_rows+p, n_leading_cols+d] != ""

    if prettify:
        # Add header for OFF count column
        df.iloc[1, n_leading_cols + len(ctx.dates.items) + 1] = "OFF"
        
        # Count OFF days for each person (rows)
        for p in range(len(ctx.people.items)):
            off_count = sum(1 for d in range(len(ctx.dates.items)) 
                           if solver.Value(ctx.offs[(d, p)]) == 1)
            df.iloc[n_leading_rows + p, n_leading_cols + len(ctx.dates.items) + 1] = off_count
        
        # Add shift type count rows for each date (columns)
        # First add an empty row
        empty_row_index = n_leading_rows + len(ctx.people.items) + n_trailing_rows
        
        # Then add one row for each shift type
        for s in range(ctx.n_shift_types):
            shift_row_index = empty_row_index + 1 + s
            shift_type_id = ctx.shiftTypes.items[s].id
            
            # Add shift type label in the first column
            df.iloc[shift_row_index, 0] = f"{shift_type_id} Count"
            
            # Count occurrences of this shift type for each date
            for d in range(len(ctx.dates.items)):
                shift_count = sum(1 for p in range(len(ctx.people.items))
                                if solver.Value(ctx.shifts[(d, s, p)]) == 1)
                df.iloc[shift_row_index, n_leading_cols + d] = shift_count

    return df
