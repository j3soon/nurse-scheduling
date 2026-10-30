/*
 * This file is part of Nurse Scheduling Project, see <https://github.com/j3soon/nurse-scheduling>.
 *
 * Copyright (C) 2023-2026 Johnson Sun
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU Affero General Public License as
 * published by the Free Software Foundation, either version 3 of the
 * License, or (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU Affero General Public License for more details.
 *
 * You should have received a copy of the GNU Affero General Public License
 * along with this program.  If not, see <https://www.gnu.org/licenses/>.
 */

// This code is mostly AI generated.

import { formatSeconds, formatSpeed, formatUsd, turnDetailsLabel, turnMeasurementLines, type CostSummary, type ProviderCallCost } from './costs';

export function CostDetails({ summary, calls, running }: {
  summary: CostSummary; calls: ProviderCallCost[]; running: boolean;
}) {
  const knownPending = calls.filter(call => call.status === 'pending' && call.costUsd !== null).length;
  const displayed = running ? summary : { ...summary, pending: 0,
    unavailable: summary.unavailable + Math.max(0, summary.pending - knownPending) };
  return <details className="cost-details">
    <summary className="cost-summary">{turnDetailsLabel(displayed)}</summary>
    <div className="turn-metrics">{turnMeasurementLines(displayed).map(line => <div key={line}>{line}</div>)}</div>
    <ul className="cost-calls" aria-label="Provider calls">
      {calls.map((call, index) => <li key={call.callId} className="cost-call">
        <div>{index + 1}. {call.model} · {call.reasoning} · {call.costUsd !== null
          ? formatUsd(call.costUsd) : call.status === 'pending' && running ? 'Cost pending' : 'Cost unavailable'}</div>
        {call.responseModel && call.responseModel !== call.model && <div>Reported model: {call.responseModel}</div>}
        {call.usage && <div>
          Input: {call.usage.prompt_tokens.toLocaleString()} · Output: {call.usage.completion_tokens.toLocaleString()}
          {call.usage.cached_prompt_tokens != null && <> · Cached input: {call.usage.cached_prompt_tokens.toLocaleString()}</>}
          {!!call.usage.reasoning_tokens && <> · Reasoning (included in output): {call.usage.reasoning_tokens.toLocaleString()}</>}
        </div>}
        <div>Provider streaming speed: {formatSpeed(call.usage?.completion_tokens, call.streamingSeconds)}
          {call.streamingSeconds != null && <> · Streaming: {formatSeconds(call.streamingSeconds)}</>}
          {call.timeToFirstOutputSeconds != null && <> · Time to first output: {formatSeconds(call.timeToFirstOutputSeconds)}</>}
        </div>
        <div className="cost-call-id">Call: {call.providerCallId ?? call.callId}</div>
      </li>)}
    </ul>
  </details>;
}
