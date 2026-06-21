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
import { anonymizeSchedulingState, anonymizeSchedulingStateWithMapping, removeDescriptionFields } from '@/utils/anonymizeSchedulingState';

const state: SchedulingState = {
  apiVersion: 'alpha',
  description: 'schedule',
  dates: { range: {}, items: [], groups: [] },
  people: {
    items: [
      { id: 'Alice', description: 'first person' },
      { id: 'Bob', description: 'second person' }
    ],
    groups: [{ id: 'Team', members: ['Alice', 'Bob'], description: 'all people' }]
  },
  shiftTypes: { items: [{ id: 'D', description: '' }], groups: [] },
  preferences: [
    { type: 'shift request', description: 'Alice wants day', person: ['Alice'], date: ['01'], shiftType: ['D'], weight: 1 },
    { type: 'shift type requirement', qualifiedPeople: ['Team'], date: ['ALL'], shiftType: ['D'], requiredNumPeople: 1, weight: 2 },
    { type: 'shift type successions', person: ['Bob'], pattern: ['D'], date: ['ALL'], weight: 3 },
    { type: 'shift count', person: ['Alice', 'Team'], countDates: ['ALL'], countShiftTypes: ['D'], expression: 'x >= T', target: 1, weight: 4 },
    { type: 'shift affinity', people1: ['Alice'], people2: ['Team'], date: ['ALL'], shiftTypes: ['D'], weight: 5 }
  ],
  export: {
    formatting: [{ type: 'row', description: 'Highlight Alice', people: ['ALL', 'Alice', 'Team'], backgroundColor: '#ffffff' }],
    extraRows: [{ type: 'count', description: 'Count people', header: 'People', countPeople: ['ALL', 'Bob', 'Team'], countShiftTypes: ['D'] }]
  }
};

describe('anonymizeSchedulingState', () => {
  it('replaces people item IDs and item references without mutating the source state', () => {
    const result = anonymizeSchedulingState(state, {
      anonymizePeopleItems: true,
      anonymizePeopleGroups: false
    });

    expect(result.people.items.map(item => item.id)).toEqual(['P1', 'P2']);
    expect(result.people.groups).toEqual([{ id: 'Team', members: ['P1', 'P2'], description: 'all people' }]);
    expect(result.preferences).toEqual([
      { type: 'shift request', description: 'Alice wants day', person: ['P1'], date: ['01'], shiftType: ['D'], weight: 1 },
      { type: 'shift type requirement', qualifiedPeople: ['Team'], date: ['ALL'], shiftType: ['D'], requiredNumPeople: 1, weight: 2 },
      { type: 'shift type successions', person: ['P2'], pattern: ['D'], date: ['ALL'], weight: 3 },
      { type: 'shift count', person: ['P1', 'Team'], countDates: ['ALL'], countShiftTypes: ['D'], expression: 'x >= T', target: 1, weight: 4 },
      { type: 'shift affinity', people1: ['P1'], people2: ['Team'], date: ['ALL'], shiftTypes: ['D'], weight: 5 }
    ]);
    expect(result.export?.formatting?.[0]).toMatchObject({ people: ['ALL', 'P1', 'Team'] });
    expect(result.export?.extraRows?.[0]).toMatchObject({ countPeople: ['ALL', 'P2', 'Team'] });
    expect(state.people.items.map(item => item.id)).toEqual(['Alice', 'Bob']);
  });

  it('replaces nested affinity people references in imported backend syntax', () => {
    const nestedState: SchedulingState = {
      ...state,
      preferences: [
        {
          type: 'shift affinity',
          people1: [['Alice', 'Team']] as unknown as string[],
          people2: [['Bob']] as unknown as string[],
          date: ['ALL'],
          shiftTypes: ['D'],
          weight: 5
        }
      ]
    };

    const result = anonymizeSchedulingState(nestedState, {
      anonymizePeopleItems: true,
      anonymizePeopleGroups: false
    });

    expect(result.preferences[0]).toMatchObject({
      people1: [['P1', 'Team']],
      people2: [['P2']],
    });
  });

  it('replaces people group IDs and references independently', () => {
    const result = anonymizeSchedulingState(state, {
      anonymizePeopleItems: false,
      anonymizePeopleGroups: true
    });

    expect(result.people.items.map(item => item.id)).toEqual(['Alice', 'Bob']);
    expect(result.people.groups).toEqual([{ id: 'G1', members: ['Alice', 'Bob'], description: 'all people' }]);
    expect(result.preferences[1]).toMatchObject({ qualifiedPeople: ['G1'] });
    expect(result.preferences[3]).toMatchObject({ person: ['Alice', 'G1'] });
    expect(result.preferences[4]).toMatchObject({ people2: ['G1'] });
    expect(result.export?.formatting?.[0]).toMatchObject({ people: ['ALL', 'Alice', 'G1'] });
    expect(result.export?.extraRows?.[0]).toMatchObject({ countPeople: ['ALL', 'Bob', 'G1'] });
  });

  it('returns a reverse mapping for restoring anonymized IDs', () => {
    const result = anonymizeSchedulingStateWithMapping(state, {
      anonymizePeopleItems: true,
      anonymizePeopleGroups: false
    });

    expect(result.originalIdByAnonymizedId).toEqual(new Map([
      ['P1', 'Alice'],
      ['P2', 'Bob']
    ]));
  });

  it('removes description fields when requested', () => {
    const result = anonymizeSchedulingState(state, {
      anonymizePeopleItems: true,
      anonymizePeopleGroups: false,
      removeDescriptions: true
    });

    expect(result).toEqual(removeDescriptionFields(result));
    expect('description' in result).toBe(false);
    expect(result.people.items).toEqual([{ id: 'P1' }, { id: 'P2' }]);
    expect(result.people.groups).toEqual([{ id: 'Team', members: ['P1', 'P2'] }]);
    expect(result.preferences[0]).toEqual({
      type: 'shift request',
      person: ['P1'],
      date: ['01'],
      shiftType: ['D'],
      weight: 1
    });
    expect(result.export?.formatting?.[0]).toEqual({
      type: 'row',
      people: ['ALL', 'P1', 'Team'],
      backgroundColor: '#ffffff'
    });
    expect(result.export?.extraRows?.[0]).toEqual({
      type: 'count',
      header: 'People',
      countPeople: ['ALL', 'P2', 'Team'],
      countShiftTypes: ['D']
    });
    expect(state.description).toBe('schedule');
  });
});
