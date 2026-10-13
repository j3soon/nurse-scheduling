<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- SPDX-FileCopyrightText: 2026 Johnson Sun -->
<!-- This file is mostly AI generated. -->

# Guide and prefix-cache experiments

Before embedding a guide, check whether the current agent already reads it.
Keep guide availability unchanged when comparing ways to direct the agent to
it. Separate gains from better answers, fewer document reads, and cache reuse.
If testing cache reuse, verify provider usage and timing with matched cold and
warm requests. Keep output length and shared prompt content comparable. A
configured cache is not proof of a hit. An unreported cache count is unknown,
not zero. Use the existing cache probe rather than guessing from latency alone.

- [Prefix-cache probe](../../../core/tests/ai_eval/prefix_cache_probe.py) for cache
  experiments. Inspect its CLI before choosing probe or benchmark mode.
