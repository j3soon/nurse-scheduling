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

export type ProgressEvent = {
  type: 'phase' | 'solution' | 'completed' | 'failed';
  code: string;
  message: string;
  progress?: number;
  score?: number;
  solution_count?: number;
  elapsed_seconds?: number;
};

const PROGRESS_MESSAGES: Record<string, string> = {
  loading_scenario: 'Loading schedule configuration...',
  parsing_data: 'Parsing schedule data...',
  initializing_solver: 'Initializing solver...',
  creating_shift_variables: 'Creating shift variables...',
  creating_off_variables: 'Creating off variables...',
  creating_lookup_maps: 'Creating lookup indexes...',
  adding_preferences: 'Adding preferences and constraints...',
  solving: 'Solving schedule...',
  solution_found: 'Found an improved solution',
  exporting: 'Preparing schedule output...',
  schedule_completed: 'Schedule solved; generating Excel...',
  completed: 'Optimization completed.',
  failed: 'Optimization failed',
};

export function formatProgressMessage(event: ProgressEvent): string {
  const label = PROGRESS_MESSAGES[event.code] ?? event.message;

  if (event.type === 'solution') {
    const details = [
      event.score !== undefined ? `score ${event.score}` : null,
      event.solution_count !== undefined ? `solution ${event.solution_count}` : null,
      event.elapsed_seconds !== undefined ? `${event.elapsed_seconds.toFixed(1)}s elapsed` : null,
    ].filter(Boolean);
    return details.length > 0 ? `${label}: ${details.join(', ')}` : label;
  }

  if (event.type === 'failed') {
    return `${label}: ${event.message}`;
  }

  return label;
}
