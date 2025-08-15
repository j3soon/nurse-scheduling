import pandas as pd
from ortools.sat.python import cp_model

from .context import Context


def get_people_versus_date_dataframe(ctx: Context, solver: cp_model.CpSolver):
    # Initialize dataframe with size including leading rows and columns
    n_leading_rows, n_leading_cols = 2, 1
    n_trailing_rows, n_trailing_cols = 2, 0
    df = pd.DataFrame(
        "",
        index=range(n_leading_rows + len(ctx.people.items) + n_trailing_rows),
        columns=range(n_leading_cols + len(ctx.dates.items) + n_trailing_cols)
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
    for (d, s, p) in ctx.shifts:
        if solver.Value(ctx.shifts[(d, s, p)]) == 1:
            assert df.iloc[n_leading_rows+p, n_leading_cols+d] == ""
            df.iloc[n_leading_rows+p, n_leading_cols+d] = ctx.shiftTypes.items[s].id

    # Fill objective value
    df.iloc[n_leading_rows + len(ctx.people.items), 0] = "Score"
    df.iloc[n_leading_rows + len(ctx.people.items), 1] = solver.Value(ctx.objective) # or solver.ObjectiveValue()
    # Fill solver status
    df.iloc[n_leading_rows + len(ctx.people.items) + 1, 0] = "Status"
    df.iloc[n_leading_rows + len(ctx.people.items) + 1, 1] = ctx.solver_status

    # Sanity check with offs variables
    for (d, p) in ctx.offs.keys():
        if solver.Value(ctx.offs[(d, p)]) == 1:
            assert df.iloc[n_leading_rows+p, n_leading_cols+d] == ""
        else:
            assert df.iloc[n_leading_rows+p, n_leading_cols+d] != ""

    return df
