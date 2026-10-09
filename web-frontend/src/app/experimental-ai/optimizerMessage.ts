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

const detailLabels = new Set([
  'Outcome', 'Final score', 'Solver', 'Solver status', 'Termination reason', 'Solver timeout',
  'Backend URL', 'Backend version', 'API version', 'Service', 'Deployment', 'Instance',
  'Backend request timeout', 'Claimed performance', 'Error code', 'Error',
]);

import type { OptimizationActivity } from './aiClient';

export function parseOptimizerMessage(content: string): {
  summary: string;
  details: { label: string; value: string }[];
} {
  const summary: string[] = [];
  const details: { label: string; value: string }[] = [];
  for (const line of content.split('\n')) {
    const separator = line.indexOf(': ');
    const label = line.slice(0, separator);
    if (separator >= 0 && detailLabels.has(label)) {
      details.push({ label, value: line.slice(separator + 2) });
    } else if (details.length > 0) {
      details[details.length - 1].value += `\n${line.startsWith(' ') ? line.slice(1) : line}`;
    } else {
      summary.push(line);
    }
  }
  return { summary: summary.join('\n'), details };
}

export function optimizationMessage(activity: OptimizationActivity): string {
  const summary = activity.state === 'completed'
    ? activity.downloadable
      ? 'Optimization finished. Download the optimized schedule to review it.'
      : 'Optimization finished, but no result workbook is available to download.'
    : `Optimization ended with status: ${activity.state}.`;
  const details: string[] = [];
  const add = (label: string, value: string | number | undefined) => {
    // Indent continuation lines so field values cannot introduce another label.
    if (value !== undefined) details.push(`${label}: ${String(value).replace(/\r\n?|\n/g, '\n ')}`);
  };
  add('Outcome', activity.result?.outcome);
  add('Final score', activity.result?.score);
  add('Solver', activity.request?.solver);
  add('Solver status', activity.result?.solverStatus);
  add('Termination reason', activity.result?.terminationReason);
  if (activity.request?.timeoutSeconds !== undefined) add('Solver timeout', `${activity.request.timeoutSeconds}s`);
  if (activity.backend) {
    add('Backend URL', activity.backend.url ?? 'unknown');
    add('Backend version', activity.backend.appVersion ?? 'unknown');
    add('API version', activity.backend.apiVersion);
    add('Service', activity.backend.serviceName);
    add('Deployment', activity.backend.deploymentId);
    add('Instance', activity.backend.instanceId);
    if (activity.backend.requestTimeoutSeconds !== undefined) {
      add('Backend request timeout', `${activity.backend.requestTimeoutSeconds}s`);
    }
    const claimed = activity.backend.claimedPerformance;
    add('Claimed performance', claimed ? `${claimed.score} (version ${claimed.appVersion}, measured ${claimed.measuredAt})` : 'unavailable');
  }
  add('Error code', activity.error?.code);
  add('Error', activity.error?.message);
  return [summary, ...details].join('\n');
}
