import pandas as pd


def get_people_versus_date_dataframe(
    dates, people, requirements,
    shifts, solver,
):
    # Initialize dataframe with size including leading rows and columns
    n_leading_rows, n_leading_cols = 2, 1
    df = pd.DataFrame("", index=range(n_leading_rows + len(people)), columns=range(n_leading_cols + len(dates)))

    # Fill day numbers and weekdays
    # - row 0 contains day number
    # - row 1 contains weekday
    for d, date in enumerate(dates):
        df.iloc[0, n_leading_cols + d] = date.day
        df.iloc[1, n_leading_cols + d] = date.strftime('%a')

    # Fill person descriptions
    # - column 0 contains person description
    for p, person in enumerate(people):
        df.iloc[n_leading_rows+p, 0] = person.description

    # Set cell values based on solver results
    for (d, r, p) in shifts.keys():
        if solver.Value(shifts[(d, r, p)]) == 1:
            assert df.iloc[n_leading_rows+p, n_leading_cols+d] == ""
            df.iloc[n_leading_rows+p, n_leading_cols+d] = requirements[r].id

    return df
