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

## Calendar source selection

Compare the rewritten prompt with and without an additional calendar-calculation
step. Both versions include the revised holiday-renewal instruction and the same
helper. Model: `unsloth/Qwen3.8-27B-NVFP4`, real provider and isolated E2B commands,
three repetitions and four jobs. No optimizer jobs run.

| Case | Without the additional step | With the additional step |
| --- | ---: | ---: |
| `taiwan-calendar-cross-year-summary` | 3/3 | 3/3 |
| `taiwan-calendar-unsupported-range` | 3/3 | 3/3 |
| `dates-range-renew-makeup` | 3/3 | 3/3 |

Manual review confirms generator calls with `--start` and `--end` in all six
supported-range runs per version. Some calls use a Python wrapper, redirect the
output or print formatted JSON. The conservative direct-JSON execution check
needs manual review for these forms. Unsupported-range calls correctly fail.
They are not successful calculation requirements.

No cost target was declared and neither correctness nor supported-range helper
selection improved. The comparison does not pass the benefit gate. Remove the
additional prompt step and retain the unsupported-range testcase. Older source-
selection measurements used the earlier direct-TypeScript renewal instruction
and do not establish a benefit in this revised context.

## Matched cost metrics

Means and sample standard deviations use repetitions where both arms pass without infrastructure errors.
Pairs is usable/matched repetitions. Incomplete token telemetry is excluded, never replaced with zero.
Delta is after minus before. Delta SD is computed from paired differences, not from the arm SDs.
Reported reasoning tokens are part of completion tokens and must not be added again.
Small samples describe these runs and do not establish statistical significance.

| Case | Metric | Pairs | Before mean ± SD | After mean ± SD | Delta mean ± SD | Change |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| dates-range-renew-makeup | prompt_tokens | 3/3 | 37036.7 ± 9588.0 | 34357.7 ± 5742.7 | -2679.0 ± 11447.4 | -7.2% |
| dates-range-renew-makeup | cached_prompt_tokens | 3/3 | 16533.3 ± 5619.0 | 16000.0 ± 4233.2 | -533.3 ± 6661.3 | -3.2% |
| dates-range-renew-makeup | uncached_prompt_tokens | 3/3 | 20503.3 ± 4219.5 | 18357.7 ± 1517.7 | -2145.7 ± 4796.5 | -10.5% |
| dates-range-renew-makeup | completion_tokens | 3/3 | 3199.7 ± 925.5 | 4513.0 ± 1009.6 | +1313.3 ± 89.3 | +41.0% |
| dates-range-renew-makeup | reasoning_tokens | 3/3 | 2306.3 ± 893.7 | 3659.0 ± 982.6 | +1352.7 ± 89.1 | +58.7% |
| dates-range-renew-makeup | total_tokens | 3/3 | 40236.3 ± 9955.3 | 38870.7 ± 4779.7 | -1365.7 ± 11402.5 | -3.4% |
| dates-range-renew-makeup | tool_calls | 3/3 | 5.0 ± 1.0 | 4.3 ± 0.6 | -0.7 ± 1.2 | -13.3% |
| dates-range-renew-makeup | reads | 3/3 | 2.3 ± 0.6 | 2.3 ± 0.6 | +0.0 ± 1.0 | +0.0% |
| dates-range-renew-makeup | bash_calls | 3/3 | 1.7 ± 0.6 | 1.0 ± 0.0 | -0.7 ± 0.6 | -40.0% |
| dates-range-renew-makeup | turns | 3/3 | 6.3 ± 1.5 | 5.3 ± 0.6 | -1.0 ± 1.7 | -15.8% |
| dates-range-renew-makeup | seconds | 3/3 | 55.2 ± 12.0 | 69.1 ± 13.7 | +13.8 ± 2.4 | +25.0% |
| taiwan-calendar-cross-year-summary | prompt_tokens | 3/3 | 23086.7 ± 6260.3 | 17370.3 ± 7229.2 | -5716.3 ± 12374.6 | -24.8% |
| taiwan-calendar-cross-year-summary | cached_prompt_tokens | 3/3 | 10133.3 ± 4026.6 | 7466.7 ± 4026.6 | -2666.7 ± 7390.1 | -26.3% |
| taiwan-calendar-cross-year-summary | uncached_prompt_tokens | 3/3 | 12953.3 ± 2241.9 | 9903.7 ± 3210.7 | -3049.7 ± 5031.0 | -23.5% |
| taiwan-calendar-cross-year-summary | completion_tokens | 3/3 | 2029.7 ± 918.5 | 1467.3 ± 617.9 | -562.3 ± 1466.6 | -27.7% |
| taiwan-calendar-cross-year-summary | reasoning_tokens | 3/3 | 1415.3 ± 772.0 | 1169.7 ± 523.5 | -245.7 ± 1280.1 | -17.4% |
| taiwan-calendar-cross-year-summary | total_tokens | 3/3 | 25116.3 ± 7136.7 | 18837.7 ± 7769.1 | -6278.7 ± 13666.6 | -25.0% |
| taiwan-calendar-cross-year-summary | tool_calls | 3/3 | 4.0 ± 1.0 | 2.7 ± 1.5 | -1.3 ± 2.3 | -33.3% |
| taiwan-calendar-cross-year-summary | reads | 3/3 | 1.7 ± 1.2 | 1.3 ± 1.2 | -0.3 ± 2.3 | -20.0% |
| taiwan-calendar-cross-year-summary | bash_calls | 3/3 | 2.3 ± 0.6 | 1.3 ± 0.6 | -1.0 ± 0.0 | -42.9% |
| taiwan-calendar-cross-year-summary | turns | 3/3 | 3.7 ± 0.6 | 3.0 ± 1.0 | -0.7 ± 1.2 | -18.2% |
| taiwan-calendar-cross-year-summary | seconds | 3/3 | 35.2 ± 11.1 | 27.3 ± 8.7 | -7.9 ± 17.4 | -22.5% |
| taiwan-calendar-unsupported-range | prompt_tokens | 3/3 | 18832.0 ± 4079.3 | 10314.0 ± 2636.2 | -8518.0 ± 2001.7 | -45.2% |
| taiwan-calendar-unsupported-range | cached_prompt_tokens | 3/3 | 6400.0 ± 2771.3 | 3733.3 ± 923.8 | -2666.7 ± 1847.5 | -41.7% |
| taiwan-calendar-unsupported-range | uncached_prompt_tokens | 3/3 | 12432.0 ± 1932.3 | 6580.7 ± 1712.4 | -5851.3 ± 1853.7 | -47.1% |
| taiwan-calendar-unsupported-range | completion_tokens | 3/3 | 488.3 ± 129.2 | 331.0 ± 108.5 | -157.3 ± 127.7 | -32.2% |
| taiwan-calendar-unsupported-range | reasoning_tokens | 3/3 | 281.7 ± 62.7 | 221.3 ± 92.1 | -60.3 ± 134.3 | -21.4% |
| taiwan-calendar-unsupported-range | total_tokens | 3/3 | 19320.3 ± 4188.7 | 10645.0 ± 2698.3 | -8675.3 ± 1949.9 | -44.9% |
| taiwan-calendar-unsupported-range | tool_calls | 3/3 | 3.3 ± 1.2 | 1.3 ± 0.6 | -2.0 ± 1.0 | -60.0% |
| taiwan-calendar-unsupported-range | reads | 3/3 | 0.7 ± 1.2 | 0.0 ± 0.0 | -0.7 ± 1.2 | -100.0% |
| taiwan-calendar-unsupported-range | bash_calls | 3/3 | 2.7 ± 1.2 | 1.3 ± 0.6 | -1.3 ± 0.6 | -50.0% |
| taiwan-calendar-unsupported-range | turns | 3/3 | 3.3 ± 0.6 | 2.3 ± 0.6 | -1.0 ± 0.0 | -30.0% |
| taiwan-calendar-unsupported-range | seconds | 3/3 | 16.4 ± 4.2 | 10.5 ± 1.5 | -5.9 ± 3.1 | -36.2% |


## Stored workbook comments

Use `inspect_xlsx.py --comments --range` for bounded stored legacy comment text.
The same inspector retains cell, formula/cache, style, overview and summary modes.
Comment XML streams directly without traversing worksheet cells. It reports
comments on blank cells, source parts and separate record/text truncation.
`threaded_comment_part` reports unsupported related data on the whole sheet.
It does not parse that text or imply it falls inside the selected range.

The fresh adjacent comparison uses the shared inspector and identical questions
and attachment bytes in both arms. Model: `unsloth/Qwen3.8-27B-NVFP4`, real
provider and isolated E2B commands, three repetitions and four jobs. No optimizer
jobs run. Both questions name the root JSON object and array-item field types.

| Case | Before correct | After correct | Before target-flag use | After target-flag use |
| --- | ---: | ---: | ---: | ---: |
| `xlsx-cell-comments` | 3/3 | 3/3 | 1/3 | 3/3 |
| `xlsx-no-cell-comments` | 3/3 | 3/3 | 0/3 | 3/3 |

The receipt requires both `--comments` and `--range` on both candidate cases.
The declared 10% generated-token target passes. Generated tokens fall 48.7% for
extraction and 52.5% for the empty control. All three extraction candidates use
one helper call without custom parsing. All three empty-control candidates
still write verification scripts. This comparison validates helper use and its
measured savings, not removal of all inline scripts. No infrastructure errors
occur.

The initial batch retains one candidate response with correct comment text but
a bare array instead of the required object. Clarify the container type in both
questions and rerun both arms without changing expected data or grading.
Earlier costs are not reused. The usage checker now accepts a complete multiline
JSON object before its existing JSON-lines fallback. Its regression test also
rejects either missing target flag. Discovery and failed calls remain excluded.

The affected cell-policy comparison passes all four cases 3/3 in both prefixes.
It shows no new correctness benefit and declares no cost target. Its older
receipt remains historical and is not refreshed as a new benefit. Separately,
24 parent/candidate CLI comparisons preserve existing cell-mode output.
Deterministic tests cover rich text, relative relationships, blank-cell comments,
threaded-part presence, truncation, incompatible flags and standalone execution.

## Matched cost metrics

Means and sample standard deviations use repetitions where both arms pass without infrastructure errors.
Pairs is usable/matched repetitions. Incomplete token telemetry is excluded, never replaced with zero.
Delta is after minus before. Delta SD is computed from paired differences, not from the arm SDs.
Reported reasoning tokens are part of completion tokens and must not be added again.
Small samples describe these runs and do not establish statistical significance.

| Case | Metric | Pairs | Before mean ± SD | After mean ± SD | Delta mean ± SD | Change |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| xlsx-cell-comments | prompt_tokens | 3/3 | 15914.0 ± 3255.9 | 9023.0 ± 0.0 | -6891.0 ± 3255.9 | -43.3% |
| xlsx-cell-comments | cached_prompt_tokens | 3/3 | 6400.0 ± 1600.0 | 3200.0 ± 0.0 | -3200.0 ± 1600.0 | -50.0% |
| xlsx-cell-comments | uncached_prompt_tokens | 3/3 | 9514.0 ± 1883.6 | 5823.0 ± 0.0 | -3691.0 ± 1883.6 | -38.8% |
| xlsx-cell-comments | completion_tokens | 3/3 | 618.7 ± 146.3 | 317.7 ± 96.6 | -301.0 ± 213.1 | -48.7% |
| xlsx-cell-comments | reasoning_tokens | 3/3 | 333.7 ± 33.1 | 178.0 ± 89.2 | -155.7 ± 121.7 | -46.7% |
| xlsx-cell-comments | total_tokens | 3/3 | 16532.7 ± 3395.8 | 9340.7 ± 96.6 | -7192.0 ± 3468.1 | -43.5% |
| xlsx-cell-comments | tool_calls | 3/3 | 2.3 ± 0.6 | 1.0 ± 0.0 | -1.3 ± 0.6 | -57.1% |
| xlsx-cell-comments | reads | 3/3 | 0.0 ± 0.0 | 0.0 ± 0.0 | +0.0 ± 0.0 | n/a |
| xlsx-cell-comments | bash_calls | 3/3 | 2.3 ± 0.6 | 1.0 ± 0.0 | -1.3 ± 0.6 | -57.1% |
| xlsx-cell-comments | turns | 3/3 | 3.3 ± 0.6 | 2.0 ± 0.0 | -1.3 ± 0.6 | -40.0% |
| xlsx-cell-comments | seconds | 3/3 | 18.1 ± 1.4 | 11.8 ± 1.0 | -6.3 ± 1.5 | -34.9% |
| xlsx-no-cell-comments | prompt_tokens | 3/3 | 24236.3 ± 4636.5 | 15465.0 ± 3102.2 | -8771.3 ± 3475.6 | -36.2% |
| xlsx-no-cell-comments | cached_prompt_tokens | 3/3 | 10133.3 ± 3330.7 | 5333.3 ± 923.8 | -4800.0 ± 2771.3 | -47.4% |
| xlsx-no-cell-comments | uncached_prompt_tokens | 3/3 | 14103.0 ± 1322.0 | 10131.7 ± 2178.5 | -3971.3 ± 1807.1 | -28.2% |
| xlsx-no-cell-comments | completion_tokens | 3/3 | 1302.3 ± 593.3 | 618.0 ± 121.9 | -684.3 ± 509.2 | -52.5% |
| xlsx-no-cell-comments | reasoning_tokens | 3/3 | 848.3 ± 514.6 | 372.3 ± 73.9 | -476.0 ± 461.9 | -56.1% |
| xlsx-no-cell-comments | total_tokens | 3/3 | 25538.7 ± 5126.2 | 16083.0 ± 3192.5 | -9455.7 ± 3984.0 | -37.0% |
| xlsx-no-cell-comments | tool_calls | 3/3 | 4.0 ± 1.0 | 2.3 ± 0.6 | -1.7 ± 0.6 | -41.7% |
| xlsx-no-cell-comments | reads | 3/3 | 0.0 ± 0.0 | 0.0 ± 0.0 | +0.0 ± 0.0 | n/a |
| xlsx-no-cell-comments | bash_calls | 3/3 | 4.0 ± 1.0 | 2.3 ± 0.6 | -1.7 ± 0.6 | -41.7% |
| xlsx-no-cell-comments | turns | 3/3 | 4.7 ± 0.6 | 3.3 ± 0.6 | -1.3 ± 0.6 | -28.6% |
| xlsx-no-cell-comments | seconds | 3/3 | 29.7 ± 7.6 | 18.1 ± 0.7 | -11.6 ± 7.1 | -39.1% |
