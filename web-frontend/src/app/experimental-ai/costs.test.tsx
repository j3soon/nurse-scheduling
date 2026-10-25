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

// This test is mostly AI generated.

import { render, screen } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import { cleanup } from '@testing-library/react';
import { CostDetails } from './CostDetails';
import { costLabel, formatUsd, isCostSummary, latestCostSummary, replaceCall, type ProviderCallCost } from './costs';

const call: ProviderCallCost = {
  callId: 'a', model: 'model', reasoning: 'high', status: 'pending', costUsd: null,
  providerCallId: null, responseModel: null, usage: null,
};
afterEach(cleanup);

it('replaces a streamed call record without counting it twice', () => {
  const pending = replaceCall(undefined, call);
  const completed = { ...call, status: 'reported' as const, costUsd: '0.01' };
  expect(replaceCall(pending, completed)).toEqual([completed]);
  expect(replaceCall([completed], completed)).toEqual([completed]);
});

it('shows missing pricing separately from an explicitly free call', () => {
  render(<CostDetails summary={{ usd: '0', calls: 2, pending: 0, unavailable: 1 }} running={false}
    calls={[{ ...call, status: 'unavailable' }, { ...call, callId: 'b', status: 'reported', costUsd: '0' }]} />);
  expect(screen.getByText('Estimated turn cost: $0.0000 · 2 calls · 1 unavailable')).toBeInTheDocument();
  expect(screen.getByText(/1\. model.*Cost unavailable/)).toBeInTheDocument();
  expect(screen.getByText(/2\. model.*\$0.0000/)).toBeInTheDocument();
});

it('shows interrupted pending calls as unavailable and does not add reasoning tokens to output', () => {
  render(<CostDetails summary={{ usd: '0.1', calls: 1, pending: 1, unavailable: 0 }} running={false}
    calls={[{ ...call, usage: { prompt_tokens: 100, completion_tokens: 20, total_tokens: 120, reasoning_tokens: 10 } }]} />);
  expect(screen.getByText('Estimated turn cost: $0.1000 · 1 call · 1 unavailable')).toBeInTheDocument();
  expect(screen.getByText(/Reasoning \(included in output\): 10/)).toBeInTheDocument();
});

it('validates cost summaries and keeps tiny nonzero estimates visible', () => {
  expect(isCostSummary({ usd: 'NaN', calls: 0, pending: 0, unavailable: 0 })).toBe(false);
  expect(isCostSummary({ usd: '0.1', calls: 1, pending: 1, unavailable: 1 })).toBe(false);
  expect(formatUsd('1e-8')).toBe('<$0.000001');
  expect(isCostSummary({ usd: '4.45E-322', calls: 1, pending: 0, unavailable: 0 })).toBe(true);
  expect(formatUsd('4.45E-322')).toBe('<$0.000001');
});

it('keeps an authoritative reset total when older foreground events are acknowledged later', () => {
  const restored = { usd: '0.2', calls: 2, pending: 0, unavailable: 0, version: 1000000 };
  const deferred = { usd: '0.1', calls: 1, pending: 0, unavailable: 0, version: 5 };
  expect(latestCostSummary(restored, deferred)).toBe(restored);
  expect(latestCostSummary(restored, { ...restored, usd: '0.3', version: 1000001 }).usd).toBe('0.3');
});

it('keeps a reported price when the process stops before the terminal call event', () => {
  render(<CostDetails summary={{ usd: '0.1', calls: 1, pending: 1, unavailable: 0 }} running={false}
    calls={[{ ...call, costUsd: '0.1' }]} />);
  expect(screen.getByText('Estimated turn cost: $0.1000 · 1 call')).toBeInTheDocument();
  expect(costLabel({ usd: '0.1', calls: 1, pending: 1, unavailable: 0 }, false)).toBe('$0.1000');
  expect(costLabel({ usd: '0.1', calls: 1, pending: 1, unavailable: 0 }, true)).toBe('$0.1000 · 1 call · 1 pending');
});
