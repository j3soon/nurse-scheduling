import pandas as pd

from .context import Context


def get_people_versus_date_dataframe(ctx: Context, solver):
    # Initialize dataframe with size including leading rows and columns
    n_leading_rows, n_leading_cols = 2, 1
    n_trailing_rows, n_trailing_cols = 1, 0
    df = pd.DataFrame(
        "",
        index=range(n_leading_rows + len(ctx.people) + n_trailing_rows),
        columns=range(n_leading_cols + len(ctx.dates) + n_trailing_cols)
    )

    # Fill day numbers and weekdays
    # - row 0 contains day number
    # - row 1 contains weekday
    for d, date in enumerate(ctx.dates):
        df.iloc[0, n_leading_cols + d] = date.day
        df.iloc[1, n_leading_cols + d] = date.strftime('%a')

    # Fill person descriptions
    # - column 0 contains person description
    for p, person in enumerate(ctx.people):
        df.iloc[n_leading_rows+p, 0] = person.description

    # Set cell values based on solver results
    for (d, r, p) in ctx.shifts.keys():
        if solver.Value(ctx.shifts[(d, r, p)]) == 1:
            assert df.iloc[n_leading_rows+p, n_leading_cols+d] == ""
            df.iloc[n_leading_rows+p, n_leading_cols+d] = ctx.requirements[r].id

    # Fill objective value
    df.iloc[n_leading_rows + len(ctx.people), 0] = "Score"
    df.iloc[n_leading_rows + len(ctx.people), 1] = solver.Value(ctx.objective)

    return df
