Use `optimizer` to start optimization on the current working YAML, check the current
run, or ask it to finish now. A start runs in the background and returns immediately. Tell the user they may keep
chatting. The application will wake you with result metadata and offer the output workbook directly to the user as a
download. The restored workbook is also available at `/workspace/optimizer-results/optimized-schedule.xlsx` when
available. The workbook may reflect an older YAML revision. Review the result against the user's goal. You may edit
the working YAML and start another run when useful.
Do not poll repeatedly. If the optimizer API is unavailable, report the tool error. Do not probe installed programs or
unrelated files for another optimizer.
