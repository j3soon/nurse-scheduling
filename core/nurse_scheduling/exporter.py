import pandas as pd
from ortools.sat.python import cp_model

from .context import Context
from . import utils, models, constants


def get_people_versus_date_dataframe(ctx: Context, solver: cp_model.CpSolver, prettify: bool = False):
    # Initialize dataframe with size including leading rows and columns
    n_leading_rows, n_leading_cols = 2, 1
    n_trailing_rows, n_trailing_cols = 2, 0
    
    n_history_cols = 0
    # Add history columns after the name column (only if prettify is enabled)
    if prettify:
        max_history_length = max((len(person.history) for person in ctx.people.items if person.history), default=0)
        n_history_cols = max_history_length
    
    # Add extra columns and rows for prettify mode
    extra_cols = 4 if prettify else 0  # Empty column + 3 OFF count columns (Total, Weekday, Weekend)
    extra_rows = (1 + ctx.n_shift_types + len(ctx.shiftTypes.groups)) if prettify else 0  # Empty row + one row per shift type + one row per shift type group
    
    df = pd.DataFrame(
        "",
        index=range(n_leading_rows + len(ctx.people.items) + n_trailing_rows + extra_rows),
        columns=range(n_leading_cols + n_history_cols + len(ctx.dates.items) + n_trailing_cols + extra_cols)
    )

    # Fill history column headers (only if prettify is enabled)
    if n_history_cols > 0:
        # - row 0 contains history position labels (H-1, H-2, etc.)
        # - row 1 contains "History" label
        for h in range(n_history_cols):
            df.iloc[0, n_leading_cols + h] = f"H-{n_history_cols - h}"
            df.iloc[1, n_leading_cols + h] = "History"
    
    # Fill day numbers and weekdays
    # - row 0 contains day number
    # - row 1 contains weekday
    for d, date in enumerate(ctx.dates.items):
        col_idx = n_leading_cols + n_history_cols + d
        if ctx.dates.items[0].year != ctx.dates.items[-1].year:
            df.iloc[0, col_idx] = date.strftime('%Y/%-m/%-d')
        elif ctx.dates.items[0].month != ctx.dates.items[-1].month:
            df.iloc[0, col_idx] = date.strftime('%-m/%-d')
        else:
            df.iloc[0, col_idx] = date.day
        df.iloc[1, col_idx] = date.strftime('%a')

    # Fill person descriptions and history
    # - column 0 contains person description
    # - columns 1 to n_history_cols contain history data (padded with empty strings, only if prettify)
    for p, person in enumerate(ctx.people.items):
        df.iloc[n_leading_rows+p, 0] = person.id
        
        # Fill history columns with proper padding (only if prettify is enabled)
        if n_history_cols > 0:
            if person.history:
                history = person.history
                # Pad with empty strings at the front if history is shorter than max_history_length
                max_history_length = max((len(person.history) for person in ctx.people.items if person.history), default=0)
                padded_history = [""] * (max_history_length - len(history)) + history
                for h in range(n_history_cols):
                    df.iloc[n_leading_rows+p, n_leading_cols + h] = padded_history[h]
            else:
                # Fill with empty strings if no history
                for h in range(n_history_cols):
                    df.iloc[n_leading_rows+p, n_leading_cols + h] = ""

    # Pre-filter preferences to avoid repeated filtering in the inner loop
    filtered_preferences = {}
    if prettify:
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
            
            # Store filtered preferences by (d, p) key for quick lookup
            for d in ds:
                for p in ps:
                    if (d, p) not in filtered_preferences:
                        filtered_preferences[(d, p)] = []
                    filtered_preferences[(d, p)].append({
                        'pref': pref,
                        'ss': ss,
                        'target_value': 1 if pref.weight > 0 else 0
                    })

    # Set cell values based on solver results
    for (d, p) in ctx.map_dp_s.keys():
        col_idx = n_leading_cols + n_history_cols + d
        assert df.iloc[n_leading_rows+p, col_idx] == ""
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
            # Use pre-filtered preferences for this (d, p) combination
            if (d, p) in filtered_preferences:
                for pref_data in filtered_preferences[(d, p)]:
                    pref = pref_data['pref']
                    ss = pref_data['ss']
                    target_value = pref_data['target_value']
                    for s in ss:
                        var = ctx.shifts[(d, s, p)] if s != constants.OFF_sid else ctx.offs[(d, p)]
                        if s == constants.OFF_sid:
                            cell_value += " [OFF]"
                        if solver.Value(var) != target_value:
                            cell_value += " [X]"
        df.iloc[n_leading_rows+p, col_idx] = cell_value

    # Fill objective value
    df.iloc[n_leading_rows + len(ctx.people.items), 0] = "Score"
    df.iloc[n_leading_rows + len(ctx.people.items), n_leading_cols + n_history_cols] = solver.Value(ctx.objective) # or solver.ObjectiveValue()
    # Fill solver status
    df.iloc[n_leading_rows + len(ctx.people.items) + 1, 0] = "Status"
    df.iloc[n_leading_rows + len(ctx.people.items) + 1, n_leading_cols + n_history_cols] = ctx.solver_status

    # Sanity check with offs variables
    if not prettify:
        for (d, p) in ctx.offs.keys():
            col_idx = n_leading_cols + n_history_cols + d
            if solver.Value(ctx.offs[(d, p)]) == 1:
                assert df.iloc[n_leading_rows+p, col_idx] == ""
            else:
                assert df.iloc[n_leading_rows+p, col_idx] != ""

    if prettify:
        # Add headers for OFF count columns
        off_col_start = n_leading_cols + n_history_cols + len(ctx.dates.items) + 1
        df.iloc[1, off_col_start] = "OFF (Total)"
        df.iloc[1, off_col_start + 1] = "OFF (Weekday)"
        df.iloc[1, off_col_start + 2] = "OFF (Weekend)"
        
        # Count OFF days for each person (rows)
        for p in range(len(ctx.people.items)):
            off_total = 0
            off_weekday = 0
            off_weekend = 0
            
            for d in range(len(ctx.dates.items)):
                if solver.Value(ctx.offs[(d, p)]) == 1:
                    off_total += 1
                    # Check if this date is a weekend
                    date = ctx.dates.items[d]
                    if date.weekday() >= 5:  # Saturday=5, Sunday=6
                        off_weekend += 1
                    else:
                        off_weekday += 1
            
            df.iloc[n_leading_rows + p, off_col_start] = off_total
            df.iloc[n_leading_rows + p, off_col_start + 1] = off_weekday
            df.iloc[n_leading_rows + p, off_col_start + 2] = off_weekend
        
        # Add shift type count rows for each date (columns)
        # First add an empty row
        empty_row_index = n_leading_rows + len(ctx.people.items) + n_trailing_rows
        
        # Add one row for each individual shift type
        for s in range(ctx.n_shift_types):
            shift_row_index = empty_row_index + 1 + s
            df.iloc[shift_row_index, 0] = f"{ctx.shiftTypes.items[s].id} Count"
            
            for d in range(len(ctx.dates.items)):
                shift_count = sum(1 for p in range(len(ctx.people.items))
                                  if solver.Value(ctx.shifts[(d, s, p)]) == 1)
                df.iloc[shift_row_index, n_leading_cols + n_history_cols + d] = shift_count
        
        # Add one row for each shift type group
        for g, shift_group in enumerate(ctx.shiftTypes.groups):
            shift_row_index = empty_row_index + 1 + ctx.n_shift_types + g
            df.iloc[shift_row_index, 0] = f"{shift_group.id} Count"
            
            for d in range(len(ctx.dates.items)):
                shift_count = sum(1 for p in range(len(ctx.people.items))
                                  if any(solver.Value(ctx.shifts[(d, s, p)]) == 1
                                  for member_id in shift_group.members
                                  for s in ctx.map_sid_s[member_id]))
                df.iloc[shift_row_index, n_leading_cols + n_history_cols + d] = shift_count

    # Apply weekend highlighting and borders if prettify is enabled
    if prettify:
        # Create a styler object to apply conditional formatting
        def apply_styling(df):
            # Create a style DataFrame with the same shape as the original
            style_df = pd.DataFrame('', index=df.index, columns=df.columns)
            
            # Apply light yellow background to history columns
            for col_idx in range(n_leading_cols, n_leading_cols + n_history_cols):
                for row_idx in range(len(df)):
                    style_df.iloc[row_idx, col_idx] = 'background-color: #fefce8'  # Light yellow background
            
            # Check each column to see if it represents a weekend (only date columns, not history columns)
            for col_idx in range(n_leading_cols + n_history_cols, n_leading_cols + n_history_cols + len(ctx.dates.items)):
                # Get the weekday from row 1 (second row)
                weekday = df.iloc[1, col_idx]
                
                # If it's Saturday or Sunday, highlight the entire column
                if weekday in ['Sat', 'Sun']:
                    # Apply background color to all rows in this column
                    for row_idx in range(len(df)):
                        style_df.iloc[row_idx, col_idx] = 'background-color: #dbeafe'  # Light blue background
            
            # Add borders to separate regions
            # Horizontal borders
            header_row_end = n_leading_rows - 1  # End of header region
            people_row_end = header_row_end + len(ctx.people.items)  # End of people region
            summary_row_end = people_row_end + n_trailing_rows  # End of summary region
            individual_counts_row_end = summary_row_end + 1 + ctx.n_shift_types  # End of individual shift type counts
            group_counts_row_end = individual_counts_row_end + len(ctx.shiftTypes.groups)  # End of group counts
            
            # Vertical borders  
            name_col_end = n_leading_cols - 1  # End of name column
            history_col_end = name_col_end + n_history_cols  # End of history columns
            date_col_end = history_col_end + len(ctx.dates.items)  # End of date columns
            off_weekend_col_end = date_col_end + 1 + 3  # End of OFF (weekend) count column
            
            # Apply borders to all cells, then add specific border styles
            for row_idx in range(len(df)):
                for col_idx in range(len(df.columns)):
                    base_style = style_df.iloc[row_idx, col_idx]
                    borders = []
                    
                    # Add horizontal borders
                    if row_idx in [header_row_end, people_row_end, summary_row_end, individual_counts_row_end, group_counts_row_end]:
                        borders.append('border-bottom: 2px solid #374151')
                    
                    # Add vertical borders
                    if col_idx in [name_col_end, history_col_end, date_col_end, off_weekend_col_end]:
                        borders.append('border-right: 2px solid #374151')
                    
                    # Combine base style with borders
                    if borders:
                        border_style = '; '.join(borders)
                        if base_style:
                            style_df.iloc[row_idx, col_idx] = f"{base_style}; {border_style}"
                        else:
                            style_df.iloc[row_idx, col_idx] = border_style
            
            return style_df
        
        # Apply the styling and return the styled DataFrame
        styled_df = df.style.apply(lambda x: apply_styling(df), axis=None)
        return styled_df
    
    return df
