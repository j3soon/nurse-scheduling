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

export interface CostSummary {
  version?: number;
  usd: string;
  calls: number;
  pending: number;
  unavailable: number;
}

export interface ProviderCallCost {
  callId: string;
  model: string;
  reasoning: string;
  status: 'pending' | 'reported' | 'unavailable';
  costUsd: string | null;
  providerCallId: string | null;
  responseModel: string | null;
  usage: { prompt_tokens: number; completion_tokens: number; total_tokens: number;
    cached_prompt_tokens?: number | null; reasoning_tokens?: number } | null;
}

export function isUsd(value: unknown): value is string {
  return typeof value === 'string' && value.length <= 80 && /^\d+(?:\.\d+)?(?:[eE][+-]?\d+)?$/.test(value)
    && Number.isFinite(Number(value)) && Number(value) >= 0;
}

export function isCostSummary(value: unknown): value is CostSummary {
  if (!value || typeof value !== 'object') return false;
  const item = value as CostSummary;
  return isUsd(item.usd) && [item.calls, item.pending, item.unavailable].every(count => Number.isSafeInteger(count) && count >= 0)
    && (item.version === undefined || (Number.isSafeInteger(item.version) && item.version >= 0))
    && item.pending + item.unavailable <= item.calls;
}

export function latestCostSummary(previous: CostSummary | null, next: CostSummary): CostSummary {
  return (previous?.version ?? -1) > (next.version ?? -1) ? previous! : next;
}

export function isProviderCallCost(value: unknown): value is ProviderCallCost {
  if (!value || typeof value !== 'object') return false;
  const item = value as ProviderCallCost;
  const usage = item.usage;
  return typeof item.callId === 'string' && !!item.callId && typeof item.model === 'string' && typeof item.reasoning === 'string'
    && ['pending', 'reported', 'unavailable'].includes(item.status)
    && (item.costUsd === null || isUsd(item.costUsd))
    && (item.status !== 'reported' || item.costUsd !== null)
    && (item.providerCallId === null || typeof item.providerCallId === 'string')
    && (item.responseModel === null || typeof item.responseModel === 'string')
    && (usage === null || (typeof usage === 'object' && !!usage
      && [usage.prompt_tokens, usage.completion_tokens, usage.total_tokens].every(count => Number.isSafeInteger(count) && count >= 0)
      && [usage.cached_prompt_tokens, usage.reasoning_tokens].every(count => count == null || (Number.isSafeInteger(count) && count >= 0))));
}

export function formatUsd(value: string): string {
  const amount = Number(value);
  if (amount > 0 && amount < 0.000001) return '<$0.000001';
  return `$${amount.toLocaleString('en-US', { minimumFractionDigits: 4, maximumFractionDigits: 6 })}`;
}

export function costLabel(summary: CostSummary, includeCalls = true): string {
  return formatUsd(summary.usd) + (includeCalls ? ` · ${summary.calls} ${summary.calls === 1 ? 'call' : 'calls'}` : '')
    + (includeCalls && summary.pending ? ` · ${summary.pending} pending` : '')
    + (summary.unavailable ? ` · ${summary.unavailable} unavailable` : '');
}

export function replaceCall(calls: ProviderCallCost[] | undefined, call: ProviderCallCost): ProviderCallCost[] {
  if (!calls?.some(item => item.callId === call.callId)) return [...(calls ?? []), call];
  return calls.map(item => item.callId === call.callId ? call : item);
}
