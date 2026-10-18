<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- SPDX-FileCopyrightText: 2026 Johnson Sun -->
<!-- This file is mostly AI generated. -->

# Helper comparisons

## Aggregate roster summaries

Compare per-person statistics with aggregate totals and run distributions,
including a catalog that describes the new output and `--summary-only` mode.
The production prompt, cases, fixtures and provider are unchanged. Inspector
output and its catalog change together. Model: `unsloth/Qwen3.8-27B-NVFP4`.
Both versions use real provider and isolated E2B commands, three repetitions,
four jobs and a 900-second test-only turn limit. Optimizer submissions are
simulated with solver-verified assignments exported as real XLSX files.

| Case | Before correct | After correct | Before statistics use | After statistics use |
| --- | ---: | ---: | ---: | ---: |
| `result-monthly-roster-statistics` | 3/3 | 3/3 | 3/3 | 3/3 |
| `result-roster-statistics` | 3/3 | 3/3 | 2/3 | 3/3 |

All monthly candidates use both `--statistics` and `--summary-only`. The new
output replaces custom aggregation in two of three runs. One candidate still
checks person rows with a JSON script. No candidate parses the XLSX directly.
The small control does not need summary-only mode.

The repeated comparison passes `check-helper` with the statistics flag and the
predeclared 10% generated-token target. A separate mode check also verifies
`--summary-only`. Generated tokens fall 76.0% on the monthly case and 69.7% on
the small control. Neither version has infrastructure errors. These three-pair
measurements are directional. Earlier separate-command measurements are
historical and are not used to validate this interface.

## Matched cost metrics

Means and sample standard deviations use repetitions where both arms pass without infrastructure errors.
Pairs is usable/matched repetitions. Incomplete token telemetry is excluded, never replaced with zero.
Delta is after minus before. Delta SD is computed from paired differences, not from the arm SDs.
Reported reasoning tokens are part of completion tokens and must not be added again.
Small samples describe these runs and do not establish statistical significance.

| Case | Metric | Pairs | Before mean ± SD | After mean ± SD | Delta mean ± SD | Change |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| result-monthly-roster-statistics | prompt_tokens | 3/3 | 50001.3 ± 13748.3 | 19984.3 ± 3346.7 | -30017.0 ± 10684.1 | -60.0% |
| result-monthly-roster-statistics | cached_prompt_tokens | 3/3 | 26133.3 ± 12220.2 | 8533.3 ± 1847.5 | -17600.0 ± 10491.9 | -67.3% |
| result-monthly-roster-statistics | uncached_prompt_tokens | 3/3 | 23868.0 ± 1588.5 | 11451.0 ± 1499.2 | -12417.0 ± 939.5 | -52.0% |
| result-monthly-roster-statistics | completion_tokens | 3/3 | 6277.7 ± 3439.0 | 1507.3 ± 429.6 | -4770.3 ± 3509.4 | -76.0% |
| result-monthly-roster-statistics | reasoning_tokens | 3/3 | 5384.0 ± 3293.6 | 1144.0 ± 456.4 | -4240.0 ± 3523.3 | -78.8% |
| result-monthly-roster-statistics | total_tokens | 3/3 | 56279.0 ± 16790.4 | 21491.7 ± 3666.8 | -34787.3 ± 13796.1 | -61.8% |
| result-monthly-roster-statistics | tool_calls | 3/3 | 6.0 ± 2.0 | 3.3 ± 0.6 | -2.7 ± 2.1 | -44.4% |
| result-monthly-roster-statistics | reads | 3/3 | 0.3 ± 0.6 | 0.7 ± 0.6 | +0.3 ± 0.6 | +100.0% |
| result-monthly-roster-statistics | bash_calls | 3/3 | 5.7 ± 2.5 | 2.7 ± 0.6 | -3.0 ± 2.0 | -52.9% |
| result-monthly-roster-statistics | turns | 3/3 | 6.0 ± 1.0 | 3.7 ± 0.6 | -2.3 ± 0.6 | -38.9% |
| result-monthly-roster-statistics | seconds | 3/3 | 89.5 ± 37.5 | 32.6 ± 6.1 | -56.8 ± 37.0 | -63.5% |
| result-roster-statistics | prompt_tokens | 3/3 | 22754.3 ± 6160.4 | 16931.3 ± 211.3 | -5823.0 ± 6279.8 | -25.6% |
| result-roster-statistics | cached_prompt_tokens | 3/3 | 9600.0 ± 3200.0 | 6400.0 ± 0.0 | -3200.0 ± 3200.0 | -33.3% |
| result-roster-statistics | uncached_prompt_tokens | 3/3 | 13154.3 ± 3034.5 | 10531.3 ± 211.3 | -2623.0 ± 3128.1 | -19.9% |
| result-roster-statistics | completion_tokens | 3/3 | 2227.3 ± 1978.4 | 675.0 ± 264.5 | -1552.3 ± 1967.2 | -69.7% |
| result-roster-statistics | reasoning_tokens | 3/3 | 1910.0 ± 1946.9 | 426.0 ± 273.7 | -1484.0 ± 1983.2 | -77.7% |
| result-roster-statistics | total_tokens | 3/3 | 24981.7 ± 7054.1 | 17606.3 ± 458.4 | -7375.3 ± 7330.6 | -29.5% |
| result-roster-statistics | tool_calls | 3/3 | 4.0 ± 1.0 | 3.0 ± 1.0 | -1.0 ± 1.7 | -25.0% |
| result-roster-statistics | reads | 3/3 | 0.3 ± 0.6 | 0.7 ± 1.2 | +0.3 ± 1.5 | +100.0% |
| result-roster-statistics | bash_calls | 3/3 | 3.7 ± 0.6 | 2.3 ± 1.5 | -1.3 ± 1.2 | -36.4% |
| result-roster-statistics | turns | 3/3 | 4.0 ± 1.0 | 3.0 ± 0.0 | -1.0 ± 1.0 | -25.0% |
| result-roster-statistics | seconds | 3/3 | 40.0 ± 22.4 | 19.1 ± 1.1 | -20.9 ± 21.3 | -52.2% |
