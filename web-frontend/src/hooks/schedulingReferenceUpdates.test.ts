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

import {
  DataType,
  SHIFT_AFFINITY,
  SHIFT_COUNT,
  SHIFT_REQUEST,
  SHIFT_TYPE_REQUIREMENT,
  SHIFT_TYPE_SUCCESSIONS,
  ShiftAffinityPreference,
  ShiftCountPreference,
  ShiftRequestPreference,
  ShiftTypeRequirementsPreference,
  ShiftTypeSuccessionsPreference,
} from '@/types/scheduling';
import { SchedulingState } from './schedulingState';
import { applyReferencesForIdChange, applyReferencesForIdDeletion } from './schedulingReferenceUpdates';

function createState(): SchedulingState {
  return {
    apiVersion: 'test',
    description: '',
    dates: {
      range: {},
      items: [{ id: '2026-01-01', description: 'Jan 1' }, { id: '2026-01-02', description: 'Jan 2' }],
      groups: [{ id: 'Workday', members: ['2026-01-01'], description: '' }],
    },
    people: {
      items: [
        { id: 'P1', description: '', history: ['N', 'D'] },
        { id: 'P2', description: '', history: ['D'] },
      ],
      groups: [{ id: 'Team', members: ['P1', 'P2'], description: '' }],
    },
    shiftTypes: {
      items: [{ id: 'D', description: 'Day' }, { id: 'N', description: 'Night' }],
      groups: [{ id: 'Clinical', members: ['D', 'N'], description: '' }],
    },
    preferences: [
      {
        type: SHIFT_TYPE_REQUIREMENT,
        description: 'requirement',
        shiftType: ['D'],
        shiftTypeCoefficients: [['D', 2]],
        requiredNumPeople: 1,
        qualifiedPeople: ['P1', 'Team'],
        date: ['2026-01-01'],
        weight: 10,
      },
      {
        type: SHIFT_REQUEST,
        description: 'request',
        person: ['P1'],
        date: ['2026-01-01'],
        shiftType: ['D'],
        weight: 1,
      },
      {
        type: SHIFT_TYPE_SUCCESSIONS,
        description: 'succession',
        person: ['P1'],
        pattern: ['N', 'D'],
        date: ['2026-01-01'],
        weight: 1,
      },
      {
        type: SHIFT_COUNT,
        description: 'count',
        person: ['P1'],
        countDates: ['2026-01-01'],
        countShiftTypes: ['D', 'N'],
        countShiftTypeCoefficients: [['D', 1], ['N', 2]],
        expression: 'x = T',
        target: 1,
        weight: 1,
      },
      {
        type: SHIFT_AFFINITY,
        description: 'affinity',
        date: ['2026-01-01'],
        people1: ['P1'],
        people2: ['P2'],
        shiftTypes: ['D'],
        weight: 1,
      },
    ],
    export: {
      formatting: [
        { type: 'cell', people: ['P1'], dates: ['2026-01-01'], shiftTypes: ['D'] },
        { type: 'row', people: ['P1'] },
        { type: 'column', dates: ['2026-01-01'] },
      ],
      extraColumns: [
        {
          type: 'count',
          header: 'D Count',
          countShiftTypes: ['D', 'N'],
          countShiftTypeCoefficients: [['D', 1], ['N', 2]],
          countDates: ['2026-01-01'],
        },
      ],
      extraRows: [
        {
          type: 'count',
          header: 'D Count',
          countShiftTypes: ['D'],
          countPeople: ['P1'],
        },
      ],
    },
  };
}

describe('applyReferencesForIdChange', () => {
  it('renames people, dates, and shift types across related state', () => {
    let state = createState();

    state = applyReferencesForIdChange(state, DataType.PEOPLE, 'P1', 'Alice');
    state = applyReferencesForIdChange(state, DataType.DATES, '2026-01-01', 'Jan1');
    state = applyReferencesForIdChange(state, DataType.SHIFT_TYPES, 'D', 'Day');

    expect(state.people.items.map(person => person.history)).toEqual([['N', 'Day'], ['Day']]);

    expect(state.preferences[0] as ShiftTypeRequirementsPreference).toMatchObject({
      shiftType: ['Day'],
      shiftTypeCoefficients: [['Day', 2]],
      qualifiedPeople: ['Alice', 'Team'],
      date: ['Jan1'],
    });
    expect(state.preferences[1] as ShiftRequestPreference).toMatchObject({
      person: ['Alice'],
      date: ['Jan1'],
      shiftType: ['Day'],
    });
    expect(state.preferences[2] as ShiftTypeSuccessionsPreference).toMatchObject({
      person: ['Alice'],
      pattern: ['N', 'Day'],
      date: ['Jan1'],
    });
    expect(state.preferences[3] as ShiftCountPreference).toMatchObject({
      person: ['Alice'],
      countDates: ['Jan1'],
      countShiftTypes: ['Day', 'N'],
      countShiftTypeCoefficients: [['Day', 1], ['N', 2]],
    });
    expect(state.preferences[4] as ShiftAffinityPreference).toMatchObject({
      date: ['Jan1'],
      people1: ['Alice'],
      people2: ['P2'],
      shiftTypes: ['Day'],
    });

    expect(state.export?.formatting).toEqual([
      { type: 'cell', people: ['Alice'], dates: ['Jan1'], shiftTypes: ['Day'] },
      { type: 'row', people: ['Alice'] },
      { type: 'column', dates: ['Jan1'] },
    ]);
    expect(state.export?.extraColumns?.[0]).toMatchObject({
      countShiftTypes: ['Day', 'N'],
      countShiftTypeCoefficients: [['Day', 1], ['N', 2]],
      countDates: ['Jan1'],
    });
    expect(state.export?.extraRows?.[0]).toMatchObject({
      countShiftTypes: ['Day'],
      countPeople: ['Alice'],
    });
  });

  it('renames IDs inside nested preference reference groups', () => {
    let state = createState();
    (state.preferences[0] as ShiftTypeRequirementsPreference).shiftType = [['D', 'N']] as unknown as string[];
    (state.preferences[4] as ShiftAffinityPreference).people1 = [['P1', 'Team']] as unknown as string[];
    (state.preferences[4] as ShiftAffinityPreference).shiftTypes = [['D', 'N']] as unknown as string[];

    state = applyReferencesForIdChange(state, DataType.SHIFT_TYPES, 'D', 'Day');
    state = applyReferencesForIdChange(state, DataType.PEOPLE, 'P1', 'Alice');

    expect((state.preferences[0] as ShiftTypeRequirementsPreference).shiftType).toEqual([['Day', 'N']]);
    expect((state.preferences[4] as ShiftAffinityPreference).people1).toEqual([['Alice', 'Team']]);
    expect((state.preferences[4] as ShiftAffinityPreference).shiftTypes).toEqual([['Day', 'N']]);
  });

  it('renames scalar preference reference fields from YAML-compatible state', () => {
    let state = createState();
    (state.preferences[0] as ShiftTypeRequirementsPreference).shiftType = 'D' as unknown as string[];
    (state.preferences[1] as ShiftRequestPreference).shiftType = 'D' as unknown as string[];
    (state.preferences[3] as ShiftCountPreference).countShiftTypes = 'D' as unknown as string[];

    state = applyReferencesForIdChange(state, DataType.SHIFT_TYPES, 'D', 'Day');

    expect((state.preferences[0] as ShiftTypeRequirementsPreference).shiftType).toBe('Day');
    expect((state.preferences[1] as ShiftRequestPreference).shiftType).toBe('Day');
    expect((state.preferences[3] as ShiftCountPreference).countShiftTypes).toBe('Day');
  });
});

describe('applyReferencesForIdDeletion', () => {
  it('removes deleted people references and drops rules with empty required fields', () => {
    const state = applyReferencesForIdDeletion(createState(), DataType.PEOPLE, ['P1']);

    expect(state.preferences).toHaveLength(1);
    expect(state.preferences[0] as ShiftTypeRequirementsPreference).toMatchObject({
      qualifiedPeople: ['Team'],
    });
    expect(state.export?.formatting).toEqual([
      { type: 'column', dates: ['2026-01-01'] },
    ]);
    expect(state.export?.extraRows).toEqual([]);
  });

  it('removes deleted date references and drops empty export columns', () => {
    const state = applyReferencesForIdDeletion(createState(), DataType.DATES, ['2026-01-01']);

    expect(state.preferences).toEqual([]);
    expect(state.export?.formatting).toEqual([
      { type: 'row', people: ['P1'] },
    ]);
    expect(state.export?.extraColumns).toEqual([]);
    expect(state.export?.extraRows).toEqual([
      {
        type: 'count',
        header: 'D Count',
        countShiftTypes: ['D'],
        countPeople: ['P1'],
      },
    ]);
  });

  it('blanks deleted shift type history slots and removes shift type export references', () => {
    const state = applyReferencesForIdDeletion(createState(), DataType.SHIFT_TYPES, ['N']);

    expect(state.people.items.map(person => person.history)).toEqual([['', 'D'], ['D']]);
    expect(state.preferences[2] as ShiftTypeSuccessionsPreference).toMatchObject({
      pattern: ['D'],
    });
    expect(state.preferences[3] as ShiftCountPreference).toMatchObject({
      countShiftTypes: ['D'],
      countShiftTypeCoefficients: [['D', 1]],
    });
    expect(state.export?.extraColumns?.[0]).toMatchObject({
      countShiftTypes: ['D'],
      countShiftTypeCoefficients: [['D', 1]],
    });
  });

  it('removes deleted shift type requirement coefficients', () => {
    const initialState = createState();
    (initialState.preferences[0] as ShiftTypeRequirementsPreference).shiftType = ['D', 'N'];
    (initialState.preferences[0] as ShiftTypeRequirementsPreference).shiftTypeCoefficients = [['D', 2], ['N', 3]];

    const state = applyReferencesForIdDeletion(initialState, DataType.SHIFT_TYPES, ['D']);

    expect(state.preferences[0] as ShiftTypeRequirementsPreference).toMatchObject({
      shiftType: ['N'],
      shiftTypeCoefficients: [['N', 3]],
    });
  });

  it('removes IDs inside nested preference reference groups', () => {
    const initialState = createState();
    (initialState.preferences[0] as ShiftTypeRequirementsPreference).shiftType = [['D', 'N']] as unknown as string[];
    (initialState.preferences[4] as ShiftAffinityPreference).shiftTypes = [['D', 'N']] as unknown as string[];

    const state = applyReferencesForIdDeletion(initialState, DataType.SHIFT_TYPES, ['D']);
    const requirement = state.preferences.find(pref => pref.type === SHIFT_TYPE_REQUIREMENT) as ShiftTypeRequirementsPreference | undefined;
    const count = state.preferences.find(pref => pref.type === SHIFT_COUNT) as ShiftCountPreference | undefined;
    const affinity = state.preferences.find(pref => pref.type === SHIFT_AFFINITY) as ShiftAffinityPreference | undefined;

    expect(requirement).toMatchObject({
      shiftType: [['N']],
    });
    expect(count).toMatchObject({
      countShiftTypes: ['N'],
    });
    expect(affinity).toMatchObject({
      shiftTypes: [['N']],
    });
  });

  it('removes nested affinity people references without dropping populated groups', () => {
    const initialState = createState();
    (initialState.preferences[4] as ShiftAffinityPreference).people1 = [['P1', 'Team']] as unknown as string[];

    const state = applyReferencesForIdDeletion(initialState, DataType.PEOPLE, ['P1']);
    const affinity = state.preferences.find(pref => pref.type === SHIFT_AFFINITY) as ShiftAffinityPreference | undefined;

    expect(affinity).toMatchObject({
      people1: [['Team']],
      people2: ['P2'],
    });
  });

  it('removes scalar preference reference fields from YAML-compatible state', () => {
    const initialState = createState();
    (initialState.preferences[0] as ShiftTypeRequirementsPreference).shiftType = 'D' as unknown as string[];
    (initialState.preferences[1] as ShiftRequestPreference).shiftType = 'D' as unknown as string[];
    (initialState.preferences[3] as ShiftCountPreference).countShiftTypes = 'N' as unknown as string[];

    const state = applyReferencesForIdDeletion(initialState, DataType.SHIFT_TYPES, ['D']);
    const count = state.preferences.find(pref => pref.type === SHIFT_COUNT) as ShiftCountPreference | undefined;

    expect(state.preferences.some(pref => pref.type === SHIFT_TYPE_REQUIREMENT)).toBe(false);
    expect(state.preferences.some(pref => pref.type === SHIFT_REQUEST)).toBe(false);
    expect(count?.countShiftTypes).toBe('N');
  });
});
