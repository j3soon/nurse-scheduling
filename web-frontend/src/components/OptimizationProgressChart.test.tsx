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

import type { ReactNode } from 'react';
import { act, render, screen } from '@testing-library/react';
import OptimizationProgressChart from './OptimizationProgressChart';

vi.mock('recharts', () => ({
  CartesianGrid: () => null,
  ComposedChart: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  Line: ({ name, type }: { name: string; type: string }) => (
    <div data-testid={`${name.toLowerCase()}-line`} data-type={type} />
  ),
  ResponsiveContainer: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  Tooltip: ({ content }: { content: (props: unknown) => ReactNode }) => (
    <>
      {content({
        active: true,
        payload: [{
          payload: {
            currentBestScore: 12000,
            elapsedSeconds: 0.5,
            commentCount: 4,
            solutionIndex: 2,
            source: 'ortools/cp-sat:solution-callback',
          },
        }],
      })}
    </>
  ),
  XAxis: ({ domain }: { domain: [number, number] }) => (
    <div data-testid="elapsed-axis" data-domain-max={domain[1]} />
  ),
  YAxis: () => null,
}));

const points = [
  {
    currentBestScore: 12,
    elapsedSeconds: 0.5,
    commentCount: 4,
    solutionIndex: 2,
    source: 'ortools/cp-sat:solution-callback',
  },
  {
    currentBestScore: 9,
    elapsedSeconds: 1,
    commentCount: 2,
    solutionIndex: 3,
    source: 'ortools/cp-sat:solution-callback',
  },
];

describe('OptimizationProgressChart', () => {
  it('renders step lines and detailed hover content', () => {
    render(<OptimizationProgressChart points={points} />);

    expect(screen.getByRole('img', { name: /optimization progress chart/i })).toBeInTheDocument();
    expect(screen.getByTestId('score-line')).toHaveAttribute('data-type', 'stepAfter');
    expect(screen.getByTestId('comments-line')).toHaveAttribute('data-type', 'stepAfter');
    expect(screen.getByText('0.5s elapsed')).toBeInTheDocument();
    expect(screen.getByText('12,000')).toBeInTheDocument();
    expect(screen.getByText('#2')).toBeInTheDocument();
    expect(screen.getByText('ortools/cp-sat:solution-callback')).toBeInTheDocument();
  });

  it('expands the elapsed-time domain while active', () => {
    vi.useFakeTimers();
    vi.spyOn(performance, 'now')
      .mockReturnValueOnce(1000)
      .mockReturnValue(2250);

    render(<OptimizationProgressChart points={points} isActive />);
    expect(screen.getByTestId('elapsed-axis')).toHaveAttribute('data-domain-max', '1');

    act(() => {
      vi.advanceTimersByTime(250);
    });

    expect(Number(screen.getByTestId('elapsed-axis').getAttribute('data-domain-max'))).toBeGreaterThan(2);
    vi.useRealTimers();
  });
});
