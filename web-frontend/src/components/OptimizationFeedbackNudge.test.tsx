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
import userEvent from '@testing-library/user-event';
import OptimizationFeedbackNudge from '@/components/OptimizationFeedbackNudge';

const sendFeedback = vi.hoisted(() => vi.fn());

vi.mock('@sentry/nextjs', () => ({
  sendFeedback,
}));

const defaultProps = {
  jobId: 'job_feedback_test',
  solver: 'ortools/cp-sat',
  timeoutSeconds: 300,
  anonymized: true,
  result: {
    outcome: 'optimal' as const,
    score: 42000,
    solver_status: 'OPTIMAL',
    termination_reason: 'optimality_proven',
  },
};

describe('OptimizationFeedbackNudge', () => {
  beforeEach(() => {
    sendFeedback.mockReset();
    sendFeedback.mockResolvedValue('feedback-event-id');
  });

  it('associates a positive rating with the optimization result', async () => {
    const user = userEvent.setup();
    render(<OptimizationFeedbackNudge {...defaultProps} />);

    await user.click(screen.getByRole('button', { name: /result was useful/i }));

    expect(sendFeedback).toHaveBeenCalledWith(
      {
        message: 'Optimization result rated useful.',
        source: 'optimization-result-rating',
      },
      {
        includeReplay: false,
        captureContext: {
          tags: {
            optimization_rating: 'up',
            optimization_solver: 'ortools/cp-sat',
            optimization_outcome: 'optimal',
            optimization_solver_status: 'OPTIMAL',
            optimization_anonymized: true,
            optimization_termination_reason: 'optimality_proven',
          },
          contexts: {
            optimization_result: {
              job_id: 'job_feedback_test',
              score: 42000,
              timeout_seconds: 300,
            },
          },
        },
      },
    );
    expect(screen.getByText('Thanks for your feedback.')).toBeInTheDocument();
    expect(screen.queryByText(/lower-right corner/i)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /optimization result/i })).not.toBeInTheDocument();
  });

  it('points a negative rating to the existing Sentry feedback widget', async () => {
    const user = userEvent.setup();
    render(<OptimizationFeedbackNudge {...defaultProps} />);

    await user.click(screen.getByRole('button', { name: /result was not useful/i }));

    expect(sendFeedback).toHaveBeenCalledWith(
      expect.objectContaining({
        message: 'Optimization result rated not useful.',
        source: 'optimization-result-rating',
      }),
      expect.objectContaining({
        includeReplay: false,
        captureContext: expect.objectContaining({
          tags: expect.objectContaining({ optimization_rating: 'down' }),
        }),
      }),
    );
    expect(screen.getByText(/Feedback button in the lower-right corner/i)).toBeInTheDocument();
  });

  it('shows an error and allows retry when Sentry cannot deliver the rating', async () => {
    const user = userEvent.setup();
    sendFeedback.mockRejectedValueOnce(new Error('blocked'));
    render(<OptimizationFeedbackNudge {...defaultProps} />);

    await user.click(screen.getByRole('button', { name: /result was useful/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/may be blocked by a browser extension/i);
    expect(screen.queryByText('Thanks for your feedback.')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /result was useful/i })).toBeEnabled();

    await user.click(screen.getByRole('button', { name: /result was useful/i }));

    expect(sendFeedback).toHaveBeenCalledTimes(2);
    expect(await screen.findByText('Thanks for your feedback.')).toBeInTheDocument();
  });
});
