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
import { act, fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import OptimizationProgressChart from './OptimizationProgressChart';

vi.mock('recharts', () => ({
  CartesianGrid: () => null,
  ComposedChart: ({
    accessibilityLayer,
    children,
    className,
    data,
    style,
  }: {
    accessibilityLayer: boolean;
    children: ReactNode;
    className: string;
    data: Array<{ currentBestScore: number; elapsedSeconds: number }>;
    style: { userSelect: string; outline: string };
  }) => (
    <div
      data-testid="composed-chart"
      data-accessibility-layer={accessibilityLayer}
      data-point-count={data.length}
      data-first-elapsed={data[0]?.elapsedSeconds}
      data-first-score={data[0]?.currentBestScore}
      className={className}
      style={style}
    >
      {children}
    </div>
  ),
  Line: ({ name, type, dot }: { name: string; type: string; dot: unknown }) => (
    <div data-testid={`${name.toLowerCase()}-line`} data-type={type} data-dots={dot === false ? 'hidden' : 'shown'} />
  ),
  ReferenceDot: ({ 'aria-label': ariaLabel }: { 'aria-label': string }) => <div aria-label={ariaLabel} />,
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
  XAxis: ({ domain, hide }: { domain: [number, number]; hide?: boolean }) => (
    hide ? null : <div data-testid="elapsed-axis" data-domain-min={domain[0]} data-domain-max={domain[1]} />
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
    expect(screen.getByRole('img', { name: /optimization progress chart/i })).toHaveClass('select-none', 'outline-none');
    expect(screen.getAllByTestId('composed-chart')).toHaveLength(2);
    expect(screen.getAllByTestId('composed-chart')[0]).toHaveAttribute('data-accessibility-layer', 'false');
    expect(screen.getAllByTestId('composed-chart')[0]).toHaveStyle({ userSelect: 'none', outline: 'none' });
    expect(screen.getByTestId('score-line')).toHaveAttribute('data-type', 'stepAfter');
    expect(screen.getByTestId('comments-line')).toHaveAttribute('data-type', 'stepAfter');
    expect(screen.getByLabelText('Latest score')).toBeInTheDocument();
    expect(screen.getByLabelText('Latest comments')).toBeInTheDocument();
    expect(screen.getByText(/higher scores are better/i)).toBeInTheDocument();
    expect(screen.getByText('0.5s elapsed')).toBeInTheDocument();
    expect(screen.getByText('12,000')).toBeInTheDocument();
    expect(screen.getByText('#2')).toBeInTheDocument();
    expect(screen.getByText('ortools/cp-sat:solution-callback')).toBeInTheDocument();
  });

  it('can hide comments while keeping elapsed time visible on the score chart', async () => {
    const user = userEvent.setup();
    render(<OptimizationProgressChart points={points} />);

    await user.click(screen.getByRole('button', { name: 'Hide comments' }));

    expect(screen.queryByTestId('comments-line')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Show comments' })).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByTestId('elapsed-axis')).toBeInTheDocument();
  });

  it('keeps the elapsed-time domain end after an active job completes', () => {
    vi.useFakeTimers();
    const nowSpy = vi.spyOn(performance, 'now')
      .mockReturnValueOnce(1000)
      .mockReturnValue(2250);

    try {
      const { rerender } = render(<OptimizationProgressChart points={points} isActive />);
      expect(screen.getByTestId('elapsed-axis')).toHaveAttribute('data-domain-max', '1');

      act(() => {
        vi.advanceTimersByTime(250);
      });

      const activeDomainMax = Number(screen.getByTestId('elapsed-axis').getAttribute('data-domain-max'));
      expect(activeDomainMax).toBeGreaterThan(2);

      rerender(<OptimizationProgressChart points={points} />);

      expect(Number(screen.getByTestId('elapsed-axis').getAttribute('data-domain-max'))).toBe(activeDomainMax);
    } finally {
      vi.useRealTimers();
      nowSpy.mockRestore();
    }
  });

  it('keeps a finite x-axis span when a range contains only the latest point', () => {
    render(<OptimizationProgressChart points={[
      { currentBestScore: 12, elapsedSeconds: 1, commentCount: 4 },
      { currentBestScore: 9, elapsedSeconds: 120, commentCount: 2 },
    ]} />);

    fireEvent.click(screen.getByRole('button', { name: 'Last 1 min' }));

    const domainMin = Number(screen.getByTestId('elapsed-axis').getAttribute('data-domain-min'));
    const domainMax = Number(screen.getByTestId('elapsed-axis').getAttribute('data-domain-max'));
    expect(Number.isFinite(domainMin)).toBe(true);
    expect(Number.isFinite(domainMax)).toBe(true);
    expect(domainMin).toBeLessThan(domainMax);
    expect(domainMax).toBe(120);
  });

  it('changes the plot domain for selected ranges and hides routine dots for dense histories', async () => {
    const user = userEvent.setup();
    const densePoints = Array.from({ length: 31 }, (_, index) => ({
      currentBestScore: 1000 - index,
      elapsedSeconds: index,
      commentCount: 31 - index,
    }));

    render(<OptimizationProgressChart points={densePoints} />);
    expect(screen.getByTestId('score-line')).toHaveAttribute('data-dots', 'hidden');
    expect(screen.getByTestId('comments-line')).toHaveAttribute('data-dots', 'hidden');
    expect(screen.getByText(/points hidden/i)).toBeInTheDocument();

    expect(screen.queryByRole('button', { name: 'Improvement' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Last 1 min' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Last 10 min' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Last 25%' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Last 25' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Last 100' })).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Last 10' }));
    expect(screen.getByTestId('elapsed-axis')).toHaveAttribute('data-domain-min', '21');
    expect(screen.getByTestId('elapsed-axis')).toHaveAttribute('data-domain-max', '30');
    expect(screen.getAllByTestId('composed-chart')[0]).toHaveAttribute('data-point-count', '10');
    expect(screen.getAllByTestId('composed-chart')[0]).toHaveAttribute('data-first-elapsed', '21');
    expect(screen.getAllByTestId('composed-chart')[0]).toHaveAttribute('data-first-score', '979');
    expect(screen.getByTestId('score-line')).toHaveAttribute('data-dots', 'shown');
    expect(screen.getByTestId('comments-line')).toHaveAttribute('data-dots', 'shown');

    await user.click(screen.getByRole('button', { name: 'Last 50' }));
    expect(screen.getByTestId('elapsed-axis')).toHaveAttribute('data-domain-min', '0');
    expect(screen.getByTestId('score-line')).toHaveAttribute('data-dots', 'hidden');
  });
});
