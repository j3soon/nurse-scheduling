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

'use client';

import { useState } from 'react';
import * as Sentry from '@sentry/nextjs';
import { FiThumbsDown, FiThumbsUp } from 'react-icons/fi';

type OptimizationRating = 'up' | 'down';

interface OptimizationFeedbackNudgeProps {
  jobId: string;
  solver: string;
  timeoutSeconds: number;
  anonymized: boolean;
  result: {
    outcome: 'optimal' | 'feasible' | 'infeasible';
    score: number | null;
    solver_status: string;
    termination_reason: string | null;
  };
}

export default function OptimizationFeedbackNudge({
  jobId,
  solver,
  timeoutSeconds,
  anonymized,
  result,
}: OptimizationFeedbackNudgeProps) {
  const [rating, setRating] = useState<OptimizationRating | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submissionError, setSubmissionError] = useState<string | null>(null);

  const submitRating = async (nextRating: OptimizationRating) => {
    if (rating !== null || isSubmitting) {
      return;
    }

    setIsSubmitting(true);
    setSubmissionError(null);
    try {
      await Sentry.sendFeedback(
        {
          message: nextRating === 'up'
            ? 'Optimization result rated useful.'
            : 'Optimization result rated not useful.',
          source: 'optimization-result-rating',
        },
        {
          includeReplay: false,
          captureContext: {
            tags: {
              optimization_rating: nextRating,
              optimization_solver: solver,
              optimization_outcome: result.outcome,
              optimization_solver_status: result.solver_status,
              optimization_anonymized: anonymized,
              ...(result.termination_reason
                ? { optimization_termination_reason: result.termination_reason }
                : {}),
            },
            contexts: {
              optimization_result: {
                job_id: jobId,
                score: result.score,
                timeout_seconds: timeoutSeconds,
              },
            },
          },
        },
      );
      setRating(nextRating);
    } catch {
      setSubmissionError('Feedback could not be sent. It may be blocked by a browser extension or network setting. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  };

  if (rating !== null) {
    return (
      <div className="rounded-md border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-700">
        <p className="font-medium">Thanks for your feedback.</p>
        {rating === 'down' && (
          <p className="mt-1 text-gray-600">
            Please tell us what went wrong using the Feedback button in the lower-right corner.
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="rounded-md border border-gray-200 bg-gray-50 px-3 py-2">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm font-medium text-gray-700">Was this optimization result useful?</p>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => void submitRating('up')}
            disabled={isSubmitting}
            aria-label="Yes, this optimization result was useful"
            className="inline-flex items-center gap-1.5 rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 transition-colors hover:border-green-300 hover:bg-green-50 hover:text-green-700 focus:outline-none focus:ring-2 focus:ring-green-500 focus:ring-offset-2 disabled:cursor-wait disabled:opacity-60"
          >
            <FiThumbsUp className="h-4 w-4" aria-hidden="true" />
            Yes
          </button>
          <button
            type="button"
            onClick={() => void submitRating('down')}
            disabled={isSubmitting}
            aria-label="No, this optimization result was not useful"
            className="inline-flex items-center gap-1.5 rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 transition-colors hover:border-amber-300 hover:bg-amber-50 hover:text-amber-700 focus:outline-none focus:ring-2 focus:ring-amber-500 focus:ring-offset-2 disabled:cursor-wait disabled:opacity-60"
          >
            <FiThumbsDown className="h-4 w-4" aria-hidden="true" />
            No
          </button>
        </div>
      </div>
      {submissionError && (
        <p role="alert" className="mt-2 text-sm text-red-700">
          {submissionError}
        </p>
      )}
    </div>
  );
}
