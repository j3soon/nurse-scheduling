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

import type { SchedulingState } from '@/hooks/useSchedulingData';
import type { ShiftRequestPreference } from '@/types/scheduling';
import { getMissingPreferredScatterDateGroups, randomizeConcreteDateShiftRequests } from '@/utils/randomizeShiftRequests';

const dateItems = ['01', '02', '03', '04', '05', '06', '07', '08'].map(id => ({ id, description: '' }));
const dateGroups = [
  { id: 'WORKDAY', members: ['01', '02', '05', '06'], description: '' },
  { id: 'FREEDAY', members: ['03', '04', '07', '08'], description: '' }
];
const state: SchedulingState = {
  apiVersion: 'alpha',
  description: '',
  dates: { range: {}, items: [], groups: [] },
  people: { items: [{ id: 'Alice', description: '' }], groups: [{ id: 'Team', members: ['Alice'], description: '' }] },
  shiftTypes: { items: [{ id: 'D', description: '' }], groups: [] },
  preferences: [
    { type: 'shift request', person: ['Alice'], date: ['01', '02'], shiftType: ['D'], weight: 1 },
    { type: 'shift request', person: ['Alice'], date: ['04'], shiftType: ['D'], weight: -1 },
    { type: 'shift request', person: ['Alice'], date: ['WORKDAY'], shiftType: ['D'], weight: 2 },
    { type: 'shift request', person: ['Team'], date: ['03'], shiftType: ['D'], weight: 3 }
  ]
};

describe('randomizeConcreteDateShiftRequests', () => {
  it('scatters concrete-date requests while preserving categories and consecutive runs', () => {
    const result = randomizeConcreteDateShiftRequests(state, dateItems, dateGroups, () => 0);
    const requests = result.preferences as ShiftRequestPreference[];
    const consecutiveDates = requests[0].date;
    const dateIndexes = consecutiveDates.map(dateId => dateItems.findIndex(item => item.id === dateId));

    expect(dateIndexes[1] - dateIndexes[0]).toBe(1);
    expect(consecutiveDates.every(dateId => dateGroups[0].members.includes(dateId))).toBe(true);
    expect(dateGroups[1].members).toContain(requests[1].date[0]);
    expect(requests[2].date).toEqual(['WORKDAY']);
    expect(requests[3].date).toEqual(['03']);
    expect(state.preferences[0]).toMatchObject({ date: ['01', '02'] });
  });

  it('falls back to weekday and weekend groups when either preferred group is missing', () => {
    const fallbackGroups = [
      { id: 'WORKDAY', members: ['01', '02', '05', '06'], description: '' },
      { id: 'WEEKDAY', members: ['01', '02', '05', '06'], description: '' },
      { id: 'WEEKEND', members: ['03', '04', '07', '08'], description: '' }
    ];
    const result = randomizeConcreteDateShiftRequests(state, dateItems, fallbackGroups, () => 0);
    const requests = result.preferences as ShiftRequestPreference[];

    expect(getMissingPreferredScatterDateGroups(fallbackGroups)).toEqual(['FREEDAY']);
    expect(requests[0].date.every(dateId => fallbackGroups[1].members.includes(dateId))).toBe(true);
    expect(fallbackGroups[2].members).toContain(requests[1].date[0]);
  });

  it('allows consecutive runs to move when category order changes but counts stay equal', () => {
    const mixedDateItems = ['01', '02', '03', '04'].map(id => ({ id, description: '' }));
    const mixedDateGroups = [
      { id: 'WORKDAY', members: ['01', '04'], description: '' },
      { id: 'FREEDAY', members: ['02', '03'], description: '' }
    ];
    const mixedState: SchedulingState = {
      ...state,
      preferences: [{ type: 'shift request', person: ['Alice'], date: ['01', '02'], shiftType: ['D'], weight: 1 }]
    };
    const result = randomizeConcreteDateShiftRequests(mixedState, mixedDateItems, mixedDateGroups, () => 0);

    expect((result.preferences[0] as ShiftRequestPreference).date).toEqual(['03', '04']);
  });

  it('requires each date item to belong to exactly one fallback category', () => {
    expect(() => randomizeConcreteDateShiftRequests(state, dateItems, [], () => 0))
      .toThrow('Date "01" must belong to exactly one of WEEKDAY or WEEKEND.');
  });

  it('rejects backend-compatible multi-person or multi-shift requests', () => {
    const multiTargetState: SchedulingState = {
      ...state,
      preferences: [
        { type: 'shift request', person: ['Alice', 'Team'], date: ['01'], shiftType: ['D'], weight: 1 },
      ],
    };

    expect(() => randomizeConcreteDateShiftRequests(multiTargetState, dateItems, dateGroups, () => 0))
      .toThrow('Cannot scatter shift requests with multiple people or multiple shift types.');
  });
});
