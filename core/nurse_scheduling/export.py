import pandas as pd


def get_people_versus_date_dataframe(
    dates, people, requirements,
    shifts, solver,
):
    n_days = len(dates)
    n_people = len(people)
    n_requirements = len(requirements)
    # Construct dataframe with extra rows and columns
    n_leading_rows = 2
    n_leading_cols = 1
    df = pd.DataFrame(
        index=range(n_leading_rows + n_people),
        columns=range(n_leading_cols + n_days),
    )
    # Clear all cells
    df.iloc[:] = ""
    # Row 0 contains day number
    # Row 1 contains weekday
    for d, date in enumerate(dates):
        df.iloc[0, n_leading_cols+d] = date.day
        df.iloc[1, n_leading_cols+d] = date.strftime('%a')
    # Column 0 contains person description
    for p, person in enumerate(people):
        df.iloc[n_leading_rows+p, 0] = person.description
    # Set cell values based on solver results
    for (d, r, p) in shifts.keys():
        if solver.Value(shifts[(d, r, p)]) == 1:
            assert df.iloc[n_leading_rows+p, n_leading_cols+d] == ""
            df.iloc[n_leading_rows+p, n_leading_cols+d] = requirements[r].id
    return df
