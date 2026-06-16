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

import type { SchedulingState } from '@/hooks/useSchedulingData';
import { getLatestSchedulingYamlForSentry, setLatestSchedulingStateForSentry } from '@/utils/sentrySchedulingState';

it('anonymizes people item IDs and references and removes descriptions in Sentry YAML', () => {
  const state: SchedulingState = {
    apiVersion: 'alpha',
    description: 'Sensitive schedule',
    dates: { range: {}, items: [], groups: [] },
    people: {
      items: [{ id: 'Alice', description: 'First person' }, { id: 'Bob', description: 'Second person' }],
      groups: [{ id: 'Team', members: ['Alice', 'Bob'], description: 'Sensitive team' }]
    },
    shiftTypes: { items: [], groups: [] },
    preferences: [
      { type: 'shift request', description: 'Sensitive request', person: ['Alice'], date: ['ALL'], shiftType: ['OFF'], weight: 1 }
    ]
  };
  setLatestSchedulingStateForSentry(state, current => current);

  const yaml = getLatestSchedulingYamlForSentry();

  expect(yaml).toContain('id: P1');
  expect(yaml).toContain('id: P2');
  expect(yaml).toContain('members: [P1, P2]');
  expect(yaml).toContain('person: [P1]');
  expect(yaml).not.toContain('Alice');
  expect(yaml).not.toContain('Bob');
  expect(yaml).not.toContain('description:');
  expect(yaml).not.toContain('Sensitive');
});
