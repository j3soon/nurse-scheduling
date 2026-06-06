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

'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipContentProps,
  type TooltipValueType,
} from 'recharts';

export interface OptimizationProgressPoint {
  currentBestScore: number;
  elapsedSeconds: number;
  commentCount?: number | null;
  solutionIndex?: number | null;
  source?: string;
}

interface OptimizationProgressChartProps {
  points: OptimizationProgressPoint[];
  isActive?: boolean;
}

const CHART_HEIGHT = 300;
const SCORE_COLOR = '#2563eb';
const COMMENT_COLOR = '#d97706';

function formatNumber(value: number): string {
  return new Intl.NumberFormat(undefined, {
    maximumFractionDigits: 2,
  }).format(value);
}

function formatElapsedSeconds(value: number): string {
  if (value < 10) {
    return `${value.toFixed(1)}s`;
  }
  if (value < 60) {
    return `${Math.round(value)}s`;
  }

  const minutes = Math.floor(value / 60);
  const seconds = Math.round(value % 60);
  return `${minutes}m ${seconds.toString().padStart(2, '0')}s`;
}

function OptimizationProgressTooltip({
  active,
  payload,
}: TooltipContentProps<TooltipValueType, number | string>) {
  const point = payload?.[0]?.payload as OptimizationProgressPoint | undefined;

  if (!active || !point) {
    return null;
  }

  return (
    <div className="min-w-48 rounded-lg border border-gray-200 bg-white/95 px-3 py-2.5 text-xs shadow-lg backdrop-blur-sm">
      <p className="mb-2 font-semibold text-gray-900">{formatElapsedSeconds(point.elapsedSeconds)} elapsed</p>
      <dl className="space-y-1.5">
        <div className="flex items-center justify-between gap-5">
          <dt className="flex items-center gap-1.5 text-gray-500">
            <span className="h-2 w-2 rounded-full bg-blue-600" />
            Score
          </dt>
          <dd className="font-semibold tabular-nums text-blue-700">{formatNumber(point.currentBestScore)}</dd>
        </div>
        <div className="flex items-center justify-between gap-5">
          <dt className="flex items-center gap-1.5 text-gray-500">
            <span className="h-2 w-2 rounded-full bg-amber-600" />
            Comments
          </dt>
          <dd className="font-semibold tabular-nums text-amber-700">{point.commentCount ?? 'N/A'}</dd>
        </div>
        <div className="flex items-center justify-between gap-5">
          <dt className="text-gray-500">Solution</dt>
          <dd className="font-medium text-gray-800">
            {point.solutionIndex !== undefined && point.solutionIndex !== null ? `#${point.solutionIndex}` : 'N/A'}
          </dd>
        </div>
        {point.source && (
          <div className="border-t border-gray-100 pt-1.5">
            <dt className="sr-only">Source</dt>
            <dd className="max-w-64 break-words text-gray-500">{point.source}</dd>
          </div>
        )}
      </dl>
    </div>
  );
}

export default function OptimizationProgressChart({
  points,
  isActive = false,
}: OptimizationProgressChartProps) {
  const latestElapsedSeconds = points.at(-1)?.elapsedSeconds ?? 0;
  const [liveElapsedSeconds, setLiveElapsedSeconds] = useState(latestElapsedSeconds);

  useEffect(() => {
    if (!isActive) {
      return;
    }

    const startedAt = performance.now();
    const intervalId = window.setInterval(() => {
      setLiveElapsedSeconds(latestElapsedSeconds + (performance.now() - startedAt) / 1000);
    }, 250);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [isActive, latestElapsedSeconds]);

  const xDomainMax = Math.max(isActive ? liveElapsedSeconds : latestElapsedSeconds, latestElapsedSeconds, 1);
  const scoreDomain = useMemo(() => {
    const scores = points.map(point => point.currentBestScore);
    const min = Math.min(...scores);
    const max = Math.max(...scores);
    const padding = min === max ? Math.max(Math.abs(min) * 0.05, 1) : (max - min) * 0.12;
    return [min - padding, max + padding] as [number, number];
  }, [points]);

  return (
    <div className="overflow-hidden rounded-lg border border-gray-200 bg-gradient-to-b from-white to-gray-50/70 shadow-sm" data-testid="optimization-progress-chart">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-gray-100 px-4 py-3">
        <div>
          <h3 className="text-sm font-semibold text-gray-900">Incumbent Progress</h3>
          <p className="mt-0.5 text-xs text-gray-500">Hover over the chart to inspect each solution.</p>
        </div>
        <div className="flex items-center gap-4 text-xs font-medium">
          <span className="inline-flex items-center gap-1.5 text-blue-700">
            <span className="h-2 w-2 rounded-full bg-blue-600 shadow-sm shadow-blue-300" />
            Score
          </span>
          <span className="inline-flex items-center gap-1.5 text-amber-700">
            <span className="h-2 w-2 rounded-full bg-amber-600 shadow-sm shadow-amber-300" />
            Comments
          </span>
        </div>
      </div>

      <div role="img" aria-label="Optimization progress chart" className="px-2 pb-2 pt-4" style={{ height: CHART_HEIGHT }}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart
            data={points}
            margin={{ top: 8, right: 12, bottom: 8, left: 4 }}
          >
            <CartesianGrid vertical={false} stroke="#e5e7eb" strokeDasharray="3 5" />
            <XAxis
              dataKey="elapsedSeconds"
              type="number"
              domain={[0, xDomainMax]}
              tickFormatter={formatElapsedSeconds}
              tick={{ fill: '#6b7280', fontSize: 11 }}
              tickLine={false}
              axisLine={{ stroke: '#d1d5db' }}
              minTickGap={36}
              unit=""
            />
            <YAxis
              yAxisId="score"
              domain={scoreDomain}
              tickFormatter={formatNumber}
              tick={{ fill: SCORE_COLOR, fontSize: 11 }}
              tickLine={false}
              axisLine={false}
              width={52}
            />
            <YAxis
              yAxisId="comments"
              orientation="right"
              domain={['auto', 'auto']}
              allowDecimals={false}
              tickFormatter={formatNumber}
              tick={{ fill: COMMENT_COLOR, fontSize: 11 }}
              tickLine={false}
              axisLine={false}
              width={42}
            />
            <Tooltip
              content={OptimizationProgressTooltip}
              cursor={{ stroke: '#64748b', strokeDasharray: '4 4', strokeWidth: 1 }}
              animationDuration={100}
              isAnimationActive={false}
            />
            <Line
              yAxisId="score"
              type="stepAfter"
              dataKey="currentBestScore"
              name="Score"
              stroke={SCORE_COLOR}
              strokeWidth={2.5}
              dot={{ r: 4, fill: SCORE_COLOR, stroke: '#ffffff', strokeWidth: 2 }}
              activeDot={{ r: 6, fill: SCORE_COLOR, stroke: '#ffffff', strokeWidth: 2 }}
              isAnimationActive={false}
            />
            <Line
              yAxisId="comments"
              type="stepAfter"
              dataKey="commentCount"
              name="Comments"
              stroke={COMMENT_COLOR}
              strokeWidth={2}
              strokeDasharray="5 4"
              connectNulls
              dot={{ r: 3.5, fill: COMMENT_COLOR, stroke: '#ffffff', strokeWidth: 2 }}
              activeDot={{ r: 5.5, fill: COMMENT_COLOR, stroke: '#ffffff', strokeWidth: 2 }}
              isAnimationActive={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
