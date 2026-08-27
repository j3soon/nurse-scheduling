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

export interface ServerInfoResponse {
  status: string;
  service_name: string;
  api_version: string;
  app_version: string;
  jobs?: {
    running: number;
    queued: number;
    cancelling: number;
  };
  workers?: {
    online: number;
  };
}

export interface ServerInfoCheckResult {
  endpoint: string;
  index: number;
  health: ServerInfoResponse;
}

export interface SolverChoice {
  value: string;
  label: string;
  compute: 'cpu' | 'gpu';
  timeout: {
    default: number;
    minimum: number;
    maximum: number;
  };
  controls: {
    cancel_running: boolean;
    finish_now: boolean;
  };
}

export interface OptimizationOptionsResponse {
  schema_version: 'alpha';
  solver: {
    default: string;
    choices: SolverChoice[];
  };
  prettify: {
    default: boolean;
  };
}

export const LOCAL_BACKEND_API_URL = 'http://localhost:8000';
export const PRODUCTION_BACKEND_API_URL = 'https://api.nursescheduling.org';
export const SECONDARY_BACKEND_API_URL = 'https://api-secondary.nursescheduling.org';
export const EXPECTED_BACKEND_SERVICE_NAME = 'nurse-scheduling-api';
export const SUPPORTED_BACKEND_API_VERSION = '0.2.0';
export const SHOULD_DISABLE_PRODUCTION_BACKEND_API = process.env.NODE_ENV === 'test'
  || process.env.NEXT_PUBLIC_DISABLE_HOSTED_OPTIMIZE_API === '1';

export function createBackendApiCandidates(disableHostedBackends: boolean): string[] {
  return disableHostedBackends
    ? []
    : [PRODUCTION_BACKEND_API_URL, SECONDARY_BACKEND_API_URL];
}

export const BACKEND_API_CANDIDATES = process.env.NODE_ENV === 'test'
  ? [LOCAL_BACKEND_API_URL]
  : createBackendApiCandidates(SHOULD_DISABLE_PRODUCTION_BACKEND_API);

export function selectPreferredServer(results: ServerInfoCheckResult[]): ServerInfoCheckResult | undefined {
  return [...results].sort((a, b) => a.index - b.index)[0];
}

export function isOptimizationOptionsResponse(value: unknown): value is OptimizationOptionsResponse {
  if (typeof value !== 'object' || value === null) {
    return false;
  }

  const candidate = value as Partial<OptimizationOptionsResponse>;
  const solver = candidate.solver;
  const prettify = candidate.prettify;
  if (
    candidate.schema_version !== 'alpha' ||
    typeof solver !== 'object' || solver === null ||
    typeof solver.default !== 'string' ||
    !Array.isArray(solver.choices) || solver.choices.length === 0 ||
    typeof prettify !== 'object' || prettify === null ||
    typeof prettify.default !== 'boolean'
  ) {
    return false;
  }

  const choicesValid = solver.choices.every(choice => {
    if (typeof choice !== 'object' || choice === null) {
      return false;
    }
    const timeout = choice.timeout;
    const controls = choice.controls;
    const timeoutValid = (
      typeof timeout === 'object' && timeout !== null &&
      Number.isInteger(timeout.default) &&
      Number.isInteger(timeout.minimum) &&
      Number.isInteger(timeout.maximum) &&
      timeout.minimum >= 1 &&
      timeout.minimum <= timeout.default &&
      timeout.default <= timeout.maximum
    );
    return (
      typeof choice.value === 'string' && choice.value.length > 0 &&
      typeof choice.label === 'string' && choice.label.length > 0 &&
      (choice.compute === 'cpu' || choice.compute === 'gpu') &&
      timeoutValid &&
      typeof controls === 'object' && controls !== null &&
      typeof controls.cancel_running === 'boolean' &&
      typeof controls.finish_now === 'boolean'
    );
  });
  if (!choicesValid) {
    return false;
  }
  const values = solver.choices.map(choice => choice.value);
  return new Set(values).size === values.length && values.includes(solver.default);
}
