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

import { useId, useState, useEffect } from 'react';
import {
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceDot,
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

type RangePreset =
  | 'full'
  | 'last-minute'
  | 'last-ten-minutes'
  | 'last-10'
  | 'last-50';

const SCORE_CHART_HEIGHT = 250;
const COMMENT_CHART_HEIGHT = 170;
const DOT_LIMIT = 30;
const SCORE_COLOR = '#2563eb';
const COMMENT_COLOR = '#d97706';
const RANGE_PRESETS: Array<{
  value: RangePreset;
  label: string;
  pointCount?: number;
  elapsedSeconds?: number;
}> = [
  { value: 'full', label: 'Full' },
  { value: 'last-minute', label: 'Last 1 min', elapsedSeconds: 60 },
  { value: 'last-ten-minutes', label: 'Last 10 min', elapsedSeconds: 600 },
  { value: 'last-10', label: 'Last 10', pointCount: 10 },
  { value: 'last-50', label: 'Last 50', pointCount: 50 },
];

function formatNumber(value: number): string {
  return new Intl.NumberFormat(undefined, {
    maximumFractionDigits: 2,
  }).format(value);
}

function formatCompactNumber(value: number): string {
  return new Intl.NumberFormat(undefined, {
    notation: 'compact',
    maximumFractionDigits: 1,
  }).format(value);
}

function formatElapsedSeconds(value: number): string {
  if (value < 10) {
    return `${value.toFixed(1)}s`;
  }
  if (value < 60) {
    return `${Math.round(value)}s`;
  }
  if (value < 3600) {
    const minutes = Math.floor(value / 60);
    const seconds = Math.round(value % 60);
    return `${minutes}m ${seconds.toString().padStart(2, '0')}s`;
  }

  const hours = Math.floor(value / 3600);
  const minutes = Math.floor((value % 3600) / 60);
  return `${hours}h ${minutes.toString().padStart(2, '0')}m`;
}

function getRangeStartIndex(points: OptimizationProgressPoint[], preset: RangePreset): number {
  const rangePreset = RANGE_PRESETS.find(candidate => candidate.value === preset);
  if (rangePreset?.pointCount) {
    return Math.max(points.length - rangePreset.pointCount, 0);
  }
  if (rangePreset?.elapsedSeconds) {
    const latestElapsed = points.at(-1)?.elapsedSeconds ?? 0;
    const firstVisibleIndex = points.findIndex(
      point => point.elapsedSeconds >= latestElapsed - rangePreset.elapsedSeconds!
    );
    return Math.max(firstVisibleIndex, 0);
  }
  return 0;
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
    <div className="min-w-52 rounded-lg border border-gray-200 bg-white/95 px-3 py-2.5 text-xs shadow-lg backdrop-blur-sm">
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
          <dd className="font-semibold tabular-nums text-amber-700">
            {typeof point.commentCount === 'number' ? formatNumber(point.commentCount) : 'N/A'}
          </dd>
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
  const syncId = useId();
  const latestElapsedSeconds = points.at(-1)?.elapsedSeconds ?? 0;
  const [liveElapsedSeconds, setLiveElapsedSeconds] = useState(latestElapsedSeconds);
  const [rangePreset, setRangePreset] = useState<RangePreset>('full');
  const [showComments, setShowComments] = useState(true);

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

  const latestPointIndex = Math.max(points.length - 1, 0);
  const range = {
    startIndex: getRangeStartIndex(points, rangePreset),
    endIndex: latestPointIndex,
  };
  const fullDomainMax = Math.max(liveElapsedSeconds, latestElapsedSeconds, 1);
  const requestedDomainMin = rangePreset === 'full' ? 0 : points[range.startIndex]?.elapsedSeconds ?? 0;
  const requestedDomainMax = fullDomainMax;
  const minimumDomainSpan = Math.max(requestedDomainMax * 0.01, 0.1);
  const xDomain: [number, number] = [
    Math.min(requestedDomainMin, requestedDomainMax - minimumDomainSpan),
    requestedDomainMax,
  ];
  const visiblePointCount = range.endIndex - range.startIndex + 1;
  const visiblePoints = points.slice(range.startIndex, range.endIndex + 1);
  const showDots = visiblePointCount <= DOT_LIMIT;
  const latestPoint = points.at(-1);

  return (
    <div className="overflow-hidden rounded-lg border border-gray-200 bg-gradient-to-b from-white to-gray-50/70 shadow-sm" data-testid="optimization-progress-chart">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-gray-100 px-4 py-3">
        <div>
          <h3 className="text-sm font-semibold text-gray-900">Incumbent Progress</h3>
          <p className="mt-0.5 text-xs text-gray-500">
            Higher scores are better. Hover to inspect a solution.
          </p>
        </div>
        <button
          type="button"
          aria-pressed={showComments}
          onClick={() => setShowComments(current => !current)}
          className="rounded-md border border-gray-200 bg-white px-2.5 py-1.5 text-xs font-medium text-gray-600 transition-colors hover:bg-gray-50"
        >
          {showComments ? 'Hide comments' : 'Show comments'}
        </button>
      </div>

      <div
        role="img"
        aria-label="Optimization progress chart"
        className="select-none px-2 pt-3 outline-none [&_.recharts-wrapper]:select-none [&_.recharts-wrapper]:outline-none [&_svg]:select-none [&_svg]:outline-none [&_text]:select-none"
        onMouseDown={event => event.preventDefault()}
      >
        <div className="flex items-center justify-between px-2">
          <p className="text-xs font-semibold text-blue-700">Score</p>
          {!showDots && <p className="text-[11px] text-gray-400">Points hidden · hover to inspect</p>}
        </div>
        <div style={{ height: SCORE_CHART_HEIGHT }}>
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart
              data={visiblePoints}
              syncId={syncId}
              syncMethod="value"
              accessibilityLayer={false}
              className="select-none outline-none focus:outline-none"
              style={{ userSelect: 'none', outline: 'none' }}
              margin={{ top: 8, right: 12, bottom: 0, left: 4 }}
            >
              <CartesianGrid vertical={false} stroke="#e5e7eb" strokeDasharray="3 5" />
              <XAxis
                dataKey="elapsedSeconds"
                type="number"
                domain={xDomain}
                allowDataOverflow
                hide={showComments}
                tickFormatter={formatElapsedSeconds}
                tick={{ fill: '#6b7280', fontSize: 11 }}
                tickLine={false}
                axisLine={{ stroke: '#d1d5db' }}
                minTickGap={48}
              />
              <YAxis
                domain={['auto', 'auto']}
                tickCount={5}
                tickFormatter={formatCompactNumber}
                tick={{ fill: SCORE_COLOR, fontSize: 11 }}
                tickLine={false}
                axisLine={false}
                width={68}
                label={{ value: 'Score', angle: -90, position: 'insideLeft', fill: SCORE_COLOR, fontSize: 11 }}
              />
              <Tooltip
                content={OptimizationProgressTooltip}
                cursor={{ stroke: '#64748b', strokeDasharray: '4 4', strokeWidth: 1 }}
                isAnimationActive={false}
              />
              <Line
                type="stepAfter"
                dataKey="currentBestScore"
                name="Score"
                stroke={SCORE_COLOR}
                strokeWidth={2.5}
                dot={showDots ? { r: 3.5, fill: SCORE_COLOR, stroke: '#ffffff', strokeWidth: 2 } : false}
                activeDot={{ r: 6, fill: SCORE_COLOR, stroke: '#ffffff', strokeWidth: 2 }}
                isAnimationActive={false}
              />
              {latestPoint && (
                <ReferenceDot
                  x={latestPoint.elapsedSeconds}
                  y={latestPoint.currentBestScore}
                  r={6}
                  fill={SCORE_COLOR}
                  stroke="#ffffff"
                  strokeWidth={2}
                  aria-label="Latest score"
                />
              )}
            </ComposedChart>
          </ResponsiveContainer>
        </div>

        {showComments && <div className="border-t border-gray-100 pt-2">
          <p className="px-2 text-xs font-semibold text-amber-700">Comments</p>
          <div style={{ height: COMMENT_CHART_HEIGHT }}>
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart
                data={visiblePoints}
                syncId={syncId}
                syncMethod="value"
                accessibilityLayer={false}
                className="select-none outline-none focus:outline-none"
                style={{ userSelect: 'none', outline: 'none' }}
                margin={{ top: 8, right: 12, bottom: 0, left: 4 }}
              >
                <CartesianGrid vertical={false} stroke="#e5e7eb" strokeDasharray="3 5" />
                <XAxis
                  dataKey="elapsedSeconds"
                  type="number"
                  domain={xDomain}
                  allowDataOverflow
                  tickFormatter={formatElapsedSeconds}
                  tick={{ fill: '#6b7280', fontSize: 11 }}
                  tickLine={false}
                  axisLine={{ stroke: '#d1d5db' }}
                  minTickGap={48}
                />
                <YAxis
                  domain={['auto', 'auto']}
                  allowDecimals={false}
                  tickCount={4}
                  tickFormatter={formatCompactNumber}
                  tick={{ fill: COMMENT_COLOR, fontSize: 11 }}
                  tickLine={false}
                  axisLine={false}
                  width={68}
                  label={{ value: 'Comments', angle: -90, position: 'insideLeft', fill: COMMENT_COLOR, fontSize: 11 }}
                />
                <Tooltip
                  content={() => null}
                  cursor={{ stroke: '#64748b', strokeDasharray: '4 4', strokeWidth: 1 }}
                  isAnimationActive={false}
                />
                <Line
                  type="stepAfter"
                  dataKey="commentCount"
                  name="Comments"
                  stroke={COMMENT_COLOR}
                  strokeWidth={2}
                  connectNulls
                  dot={showDots ? { r: 3, fill: COMMENT_COLOR, stroke: '#ffffff', strokeWidth: 2 } : false}
                  activeDot={{ r: 5.5, fill: COMMENT_COLOR, stroke: '#ffffff', strokeWidth: 2 }}
                  isAnimationActive={false}
                />
                {latestPoint && typeof latestPoint.commentCount === 'number' && (
                  <ReferenceDot
                    x={latestPoint.elapsedSeconds}
                    y={latestPoint.commentCount}
                    r={5.5}
                    fill={COMMENT_COLOR}
                    stroke="#ffffff"
                    strokeWidth={2}
                    aria-label="Latest comments"
                  />
                )}
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </div>}
      </div>

      <div className="flex flex-wrap items-center gap-1.5 border-t border-gray-100 bg-white/70 px-4 py-2">
        <span className="mr-1 text-[11px] font-medium uppercase tracking-wide text-gray-400">Range</span>
        {RANGE_PRESETS.map(preset => (
          <button
            key={preset.value}
            type="button"
            aria-pressed={rangePreset === preset.value}
            onClick={() => setRangePreset(preset.value)}
            className={`rounded-md px-2 py-1 text-xs font-medium transition-colors ${
              rangePreset === preset.value
                ? 'bg-blue-50 text-blue-700 ring-1 ring-blue-200'
                : 'text-gray-500 hover:bg-gray-100 hover:text-gray-800'
            }`}
          >
            {preset.label}
          </button>
        ))}
      </div>
    </div>
  );
}
