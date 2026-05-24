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

import { act, renderHook, waitFor } from '@testing-library/react';
import { useSchedulingData } from '@/hooks/useSchedulingData';
import {
  DataType,
  SHIFT_AFFINITY,
  SHIFT_COUNT,
  SHIFT_REQUEST,
  SHIFT_TYPE_REQUIREMENT,
  SHIFT_TYPE_SUCCESSIONS,
  ShiftRequestPreference,
} from '@/types/scheduling';
import { ALL, OFF } from '@/utils/keywords';
import { TAIWAN_FREEDAY_GROUP_ID, TAIWAN_WORKDAY_GROUP_ID } from '@/utils/taiwanHolidays';

const STORAGE_KEY = 'nurse-scheduling-data';

describe('useSchedulingData', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it('hydrates state from localStorage on mount', async () => {
    const storedState = {
      state: {
        apiVersion: 'alpha',
        description: 'loaded from storage',
        dates: {
          range: {
            startDate: '2026-01-10T12:00:00.000Z',
            endDate: '2026-01-11T12:00:00.000Z',
          },
          items: undefined,
          groups: [],
        },
        people: {
          items: [{ id: 'P1', description: '', history: [] }],
          groups: [],
          history: [],
        },
        shiftTypes: {
          items: [{ id: 'D', description: 'Day' }],
          groups: [],
        },
        preferences: [{ type: 'at most one shift per day' }],
        export: { formatting: [] },
      },
      history: [
        {
          apiVersion: 'alpha',
          description: 'loaded from storage',
          dates: {
            range: {
              startDate: '2026-01-10T12:00:00.000Z',
              endDate: '2026-01-11T12:00:00.000Z',
            },
            items: undefined,
            groups: [],
          },
          people: {
            items: [{ id: 'P1', description: '', history: [] }],
            groups: [],
            history: [],
          },
          shiftTypes: {
            items: [{ id: 'D', description: 'Day' }],
            groups: [],
          },
          preferences: [{ type: 'at most one shift per day' }],
          export: { formatting: [] },
        },
      ],
      currentHistoryIndex: 0,
    };

    localStorage.setItem(STORAGE_KEY, JSON.stringify(storedState));

    const { result } = renderHook(() => useSchedulingData());

    await waitFor(() => {
      expect(result.current.descriptionData).toBe('loaded from storage');
    });

    expect(result.current.dateData.range.startDate).toBeInstanceOf(Date);
    expect(result.current.dateData.range.endDate).toBeInstanceOf(Date);
    expect(result.current.peopleData.items.some(item => item.id === 'P1')).toBe(true);
    expect(result.current.dateData.items.map(item => item.id)).toEqual(['10', '11']);
  });

  it('falls back to the default state and logs when localStorage.getItem throws', async () => {
    const getItemSpy = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('storage unavailable');
    });
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined);

    const { result } = renderHook(() => useSchedulingData());

    await waitFor(() => {
      expect(result.current.peopleData.items.length).toBeGreaterThan(0);
      expect(result.current.peopleData.items.map(item => item.id)).toEqual(
        expect.arrayContaining(['Person 1', 'Person 2', 'Person 3']),
      );
    });

    expect(getItemSpy).toHaveBeenCalled();
    expect(errorSpy).toHaveBeenCalledWith('Failed to load data from localStorage:', expect.any(Error));
  });

  it('persists date range updates to localStorage and keeps computed items out of stored payload', async () => {
    const { result } = renderHook(() => useSchedulingData());

    act(() => {
      result.current.updateDateRange({
        startDate: new Date(Date.UTC(2026, 2, 1, 12)),
        endDate: new Date(Date.UTC(2026, 2, 3, 12)),
      });
    });

    await waitFor(() => {
      expect(localStorage.getItem(STORAGE_KEY)).not.toBeNull();
    });

    const storedRaw = localStorage.getItem(STORAGE_KEY);
    expect(storedRaw).not.toBeNull();

    const saved = JSON.parse(storedRaw!);

    expect(saved.state.dates.range.startDate).toBe('2026-03-01');
    expect(saved.state.dates.range.endDate).toBe('2026-03-03');
    expect(saved.state.dates.items).toBeUndefined();
    expect(result.current.dateData.items.map(item => item.id)).toEqual(['01', '02', '03']);
  });

  it('logs but still updates in-memory state when localStorage.setItem throws', async () => {
    const setItemSpy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('quota exceeded');
    });
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const { result } = renderHook(() => useSchedulingData());

    act(() => {
      result.current.updateDateRange({
        startDate: new Date(Date.UTC(2026, 5, 1, 12)),
        endDate: new Date(Date.UTC(2026, 5, 2, 12)),
      });
    });

    await waitFor(() => {
      expect(result.current.dateData.items.map(item => item.id)).toEqual(['01', '02']);
    });

    expect(setItemSpy).toHaveBeenCalled();
    expect(errorSpy).toHaveBeenCalledWith('Failed to save data to localStorage:', expect.any(Error));
  });

  it('undoes and redoes date identifier format transitions across month and year boundaries', async () => {
    const { result } = renderHook(() => useSchedulingData());

    act(() => {
      result.current.updateDateRange({
        startDate: new Date('2026-05-01'),
        endDate: new Date('2026-05-02'),
      });
    });

    await waitFor(() => {
      expect(result.current.dateData.items.map(item => item.id)).toEqual(['01', '02']);
    });

    act(() => {
      result.current.updateDateRange({
        startDate: new Date('2026-05-31'),
        endDate: new Date('2026-06-01'),
      });
    });

    await waitFor(() => {
      expect(result.current.dateData.items.map(item => item.id)).toEqual(['05-31', '06-01']);
    });

    act(() => {
      result.current.updateDateRange({
        startDate: new Date('2026-12-31'),
        endDate: new Date('2027-01-01'),
      });
    });

    await waitFor(() => {
      expect(result.current.dateData.items.map(item => item.id)).toEqual(['2026-12-31', '2027-01-01']);
    });

    act(() => {
      result.current.undo();
    });
    await waitFor(() => {
      expect(result.current.dateData.items.map(item => item.id)).toEqual(['05-31', '06-01']);
    });

    act(() => {
      result.current.undo();
    });
    await waitFor(() => {
      expect(result.current.dateData.items.map(item => item.id)).toEqual(['01', '02']);
    });

    act(() => {
      result.current.redo();
    });
    await waitFor(() => {
      expect(result.current.dateData.items.map(item => item.id)).toEqual(['05-31', '06-01']);
    });

    act(() => {
      result.current.redo();
    });
    await waitFor(() => {
      expect(result.current.dateData.items.map(item => item.id)).toEqual(['2026-12-31', '2027-01-01']);
    });
  });

  it('imports and replaces Taiwan holiday groups when explicitly requested on a supported range', async () => {
    const { result } = renderHook(() => useSchedulingData());

    act(() => {
      result.current.addGroup(DataType.DATES, result.current.dateData, TAIWAN_WORKDAY_GROUP_ID, [], 'Old workday group');
      result.current.addGroup(DataType.DATES, result.current.dateData, TAIWAN_FREEDAY_GROUP_ID, [], 'Old freeday group');
    });

    act(() => {
      result.current.updateDateRange(
        {
          startDate: new Date('2026-05-01'),
          endDate: new Date('2026-05-04'),
        },
        { importTaiwanHolidays: true },
      );
    });

    await waitFor(() => {
      const workdayGroup = result.current.dateData.groups.find(group => group.id === TAIWAN_WORKDAY_GROUP_ID);
      const freedayGroup = result.current.dateData.groups.find(group => group.id === TAIWAN_FREEDAY_GROUP_ID);

      expect(workdayGroup).toEqual(expect.objectContaining({ members: ['04'] }));
      expect(freedayGroup).toEqual(expect.objectContaining({ members: ['01', '02', '03'] }));
    });
  });

  it('preserves unrelated custom date groups while replacing existing Taiwan holiday groups', async () => {
    const { result } = renderHook(() => useSchedulingData());

    act(() => {
      result.current.loadFromYaml({
        apiVersion: 'alpha',
        dates: {
          range: { startDate: '2026-05-01', endDate: '2026-05-04' },
          groups: [
            { id: 'MY_GROUP', members: ['01', '04'], description: 'Keep me' },
            { id: TAIWAN_WORKDAY_GROUP_ID, members: ['02'], description: 'Old workday group' },
            { id: TAIWAN_FREEDAY_GROUP_ID, members: ['03'], description: 'Old freeday group' },
          ],
        },
      });
    });

    act(() => {
      result.current.updateDateRange(
        {
          startDate: new Date('2026-05-01'),
          endDate: new Date('2026-05-04'),
        },
        { importTaiwanHolidays: true },
      );
    });

    await waitFor(() => {
      expect(result.current.dateData.groups.find(group => group.id === 'MY_GROUP')).toEqual(
        expect.objectContaining({ members: ['01', '04'], description: 'Keep me' }),
      );
      expect(result.current.dateData.groups.find(group => group.id === TAIWAN_WORKDAY_GROUP_ID)).toEqual(
        expect.objectContaining({ members: ['04'] }),
      );
      expect(result.current.dateData.groups.find(group => group.id === TAIWAN_FREEDAY_GROUP_ID)).toEqual(
        expect.objectContaining({ members: ['01', '02', '03'] }),
      );
    });
  });

  it('preserves custom manual date items while overwriting only generated Taiwan holiday groups', async () => {
    const { result } = renderHook(() => useSchedulingData());

    act(() => {
      result.current.loadFromYaml({
        apiVersion: 'alpha',
        dates: {
          range: { startDate: '2026-05-01', endDate: '2026-05-04' },
          items: [{ id: 'SPECIAL', description: 'Manual special day' }],
          groups: [
            { id: 'MANUAL', members: ['SPECIAL'], description: 'Keep me' },
            { id: TAIWAN_WORKDAY_GROUP_ID, members: ['02'], description: 'Old workday group' },
            { id: TAIWAN_FREEDAY_GROUP_ID, members: ['03'], description: 'Old freeday group' },
          ],
        },
      });
    });

    act(() => {
      result.current.updateDateRange(
        {
          startDate: new Date('2026-05-01'),
          endDate: new Date('2026-05-04'),
        },
        { importTaiwanHolidays: true },
      );
    });

    await waitFor(() => {
      expect(result.current.dateData.items.some(item => item.id === 'SPECIAL')).toBe(true);
      expect(result.current.dateData.groups.find(group => group.id === 'MANUAL')).toEqual(
        expect.objectContaining({ members: ['SPECIAL'], description: 'Keep me' }),
      );
      expect(result.current.dateData.groups.find(group => group.id === TAIWAN_WORKDAY_GROUP_ID)?.description).not.toBe('Old workday group');
      expect(result.current.dateData.groups.find(group => group.id === TAIWAN_FREEDAY_GROUP_ID)?.description).not.toBe('Old freeday group');
    });
  });

  it('ignores Taiwan holiday import requests for unsupported ranges', async () => {
    const { result } = renderHook(() => useSchedulingData());

    act(() => {
      result.current.updateDateRange(
        {
          startDate: new Date('2027-01-01'),
          endDate: new Date('2027-01-31'),
        },
        { importTaiwanHolidays: true },
      );
    });

    await waitFor(() => {
      expect(result.current.dateData.groups.find(group => group.id === TAIWAN_WORKDAY_GROUP_ID)).toEqual(
        expect.objectContaining({ members: [] }),
      );
      expect(result.current.dateData.groups.find(group => group.id === TAIWAN_FREEDAY_GROUP_ID)).toEqual(
        expect.objectContaining({ members: [] }),
      );
    });
  });

  it('undoes and redoes supported Taiwan holiday imports as one visible range change', async () => {
    const { result } = renderHook(() => useSchedulingData());

    act(() => {
      result.current.updateDateRange(
        {
          startDate: new Date('2026-05-01'),
          endDate: new Date('2026-05-04'),
        },
        { importTaiwanHolidays: true },
      );
    });

    await waitFor(() => {
      expect(result.current.dateData.groups.find(group => group.id === TAIWAN_WORKDAY_GROUP_ID)).toEqual(
        expect.objectContaining({ members: ['04'] }),
      );
      expect(result.current.dateData.groups.find(group => group.id === TAIWAN_FREEDAY_GROUP_ID)).toEqual(
        expect.objectContaining({ members: ['01', '02', '03'] }),
      );
    });

    act(() => {
      result.current.undo();
    });

    await waitFor(() => {
      expect(result.current.dateData.groups.find(group => group.id === TAIWAN_WORKDAY_GROUP_ID)).toEqual(
        expect.objectContaining({ members: [] }),
      );
      expect(result.current.dateData.groups.find(group => group.id === TAIWAN_FREEDAY_GROUP_ID)).toEqual(
        expect.objectContaining({ members: [] }),
      );
    });

    act(() => {
      result.current.redo();
    });

    await waitFor(() => {
      expect(result.current.dateData.groups.find(group => group.id === TAIWAN_WORKDAY_GROUP_ID)).toEqual(
        expect.objectContaining({ members: ['04'] }),
      );
      expect(result.current.dateData.groups.find(group => group.id === TAIWAN_FREEDAY_GROUP_ID)).toEqual(
        expect.objectContaining({ members: ['01', '02', '03'] }),
      );
    });
  });


  it('supports undo and redo for history-aware updates', async () => {
    const { result } = renderHook(() => useSchedulingData());

    act(() => {
      result.current.addPersonHistory('Person 1', 'D');
    });

    await waitFor(() => {
      const person1 = result.current.peopleData.items.find(item => item.id === 'Person 1');
      expect(person1?.history?.[0]).toBe('D');
    });

    act(() => {
      result.current.undo();
    });

    await waitFor(() => {
      const person1 = result.current.peopleData.items.find(item => item.id === 'Person 1');
      expect(person1?.history).toEqual([]);
    });

    act(() => {
      result.current.redo();
    });

    await waitFor(() => {
      const person1 = result.current.peopleData.items.find(item => item.id === 'Person 1');
      expect(person1?.history?.[0]).toBe('D');
    });
  });

  it('replaces the latest undo entry when replaceLatestHistoryEntry is true', async () => {
    const { result } = renderHook(() => useSchedulingData());

    act(() => {
      result.current.updatePreferencesByType(SHIFT_REQUEST, [
        {
          type: SHIFT_REQUEST,
          person: ['Person 1'],
          date: ['01'],
          shiftType: ['D'],
          weight: 2,
        },
      ]);
    });

    await waitFor(() => {
      const requests = result.current.getPreferencesByType<ShiftRequestPreference>(SHIFT_REQUEST);
      expect(requests).toEqual([
        {
          type: SHIFT_REQUEST,
          person: ['Person 1'],
          date: ['01'],
          shiftType: ['D'],
          weight: 2,
        },
      ]);
    });

    act(() => {
      result.current.updatePreferencesByType(SHIFT_REQUEST, [
        {
          type: SHIFT_REQUEST,
          person: ['Person 1'],
          date: ['01', '02'],
          shiftType: ['D'],
          weight: 2,
        },
      ], { replaceLatestHistoryEntry: true });
    });

    await waitFor(() => {
      const requests = result.current.getPreferencesByType<ShiftRequestPreference>(SHIFT_REQUEST);
      expect(requests).toEqual([
        {
          type: SHIFT_REQUEST,
          person: ['Person 1'],
          date: ['01', '02'],
          shiftType: ['D'],
          weight: 2,
        },
      ]);
    });

    act(() => {
      result.current.undo();
    });

    await waitFor(() => {
      const requests = result.current.getPreferencesByType<ShiftRequestPreference>(SHIFT_REQUEST);
      expect(requests).toEqual([]);
    });
  });

  it('replaces the latest undo entry across mixed history mutators', async () => {
    const { result } = renderHook(() => useSchedulingData());

    act(() => {
      result.current.addPersonHistory('Person 1', 'D');
      result.current.addPersonHistory('Person 1', 'N', { replaceLatestHistoryEntry: true });
      result.current.updatePersonHistory('Person 1', 0, 'A', { replaceLatestHistoryEntry: true });
    });

    await waitFor(() => {
      const person = result.current.peopleData.items.find(item => item.id === 'Person 1');
      expect(person?.history).toEqual(['A', 'D']);
    });

    act(() => {
      result.current.undo();
    });

    await waitFor(() => {
      const person = result.current.peopleData.items.find(item => item.id === 'Person 1');
      expect(person?.history).toEqual([]);
    });
  });

  it('keeps one-step undo semantics when replaceLatestHistoryEntry mixes add and update history mutators', async () => {
    const { result } = renderHook(() => useSchedulingData());

    act(() => {
      result.current.addPersonHistory('Person 1', 'D');
      result.current.addPersonHistory('Person 1', 'N', { replaceLatestHistoryEntry: true });
      result.current.updatePersonHistory('Person 1', 0, 'A', { replaceLatestHistoryEntry: true });
    });

    await waitFor(() => {
      const person = result.current.peopleData.items.find(item => item.id === 'Person 1');
      expect(person?.history).toEqual(['A', 'D']);
    });

    act(() => {
      result.current.undo();
    });

    await waitFor(() => {
      const person = result.current.peopleData.items.find(item => item.id === 'Person 1');
      expect(person?.history).toEqual([]);
    });
  });

  it('truncates redo history after undo and a new mixed replacement mutation chain', async () => {
    const { result } = renderHook(() => useSchedulingData());

    act(() => {
      result.current.updatePreferencesByType<ShiftRequestPreference>(SHIFT_REQUEST, [
        {
          type: SHIFT_REQUEST,
          person: ['Person 1'],
          date: ['01'],
          shiftType: ['D'],
          weight: 1,
        },
      ]);
    });

    await waitFor(() => {
      expect(result.current.getPreferencesByType<ShiftRequestPreference>(SHIFT_REQUEST)).toHaveLength(1);
    });

    act(() => {
      result.current.updatePreferencesByType<ShiftRequestPreference>(SHIFT_REQUEST, [
        {
          type: SHIFT_REQUEST,
          person: ['Person 1'],
          date: ['01'],
          shiftType: ['N'],
          weight: 2,
        },
      ], { replaceLatestHistoryEntry: true });
    });

    await waitFor(() => {
      const requests = result.current.getPreferencesByType<ShiftRequestPreference>(SHIFT_REQUEST);
      expect(requests).toHaveLength(1);
      expect(requests[0].shiftType).toEqual(['N']);
    });

    act(() => {
      result.current.undo();
    });

    await waitFor(() => {
      expect(result.current.getPreferencesByType<ShiftRequestPreference>(SHIFT_REQUEST)).toHaveLength(0);
    });

    act(() => {
      result.current.addPersonHistory('Person 1', 'D');
      result.current.updatePersonHistory('Person 1', 0, 'N', { replaceLatestHistoryEntry: true });
    });

    await waitFor(() => {
      const person = result.current.peopleData.items.find(item => item.id === 'Person 1');
      expect(person?.history).toEqual(['N']);
    });

    act(() => {
      result.current.redo();
    });

    await waitFor(() => {
      expect(result.current.getPreferencesByType<ShiftRequestPreference>(SHIFT_REQUEST)).toHaveLength(0);
      const person = result.current.peopleData.items.find(item => item.id === 'Person 1');
      expect(person?.history).toEqual(['N']);
    });
  });

  it('loads YAML with compatibility conversions and restores Infinity from storage', async () => {
    const { result, unmount } = renderHook(() => useSchedulingData());

    act(() => {
      result.current.loadFromYaml({
        apiVersion: 'alpha',
        description: 'yaml import',
        dates: {
          range: { startDate: '2026-04-01', endDate: '2026-04-02' },
          items: [{ id: 1, description: 'Date 1' }],
          groups: [{ id: 2, members: [1], description: 'Date Group' }],
        },
        people: {
          items: [{ id: 100, description: '', history: [] }],
          groups: [{ id: 200, members: [100], description: '' }],
          history: [],
        },
        shiftTypes: {
          items: [{ id: 300, description: 'Day' }],
          groups: [{ id: 400, members: [300], description: '' }],
        },
        preferences: [
          {
            type: SHIFT_TYPE_REQUIREMENT,
            shiftType: [300],
            requiredNumPeople: 1,
            qualifiedPeople: [100],
            weight: 3,
          },
          {
            type: SHIFT_TYPE_SUCCESSIONS,
            person: [100],
            pattern: [300, OFF],
            weight: 7,
          },
          {
            type: SHIFT_REQUEST,
            person: [100],
            date: [1],
            shiftType: [300],
            weight: Infinity,
          },
        ],
        export: { formatting: [] },
      });
    });

    await waitFor(() => {
      expect(result.current.descriptionData).toBe('yaml import');
    });

    expect(result.current.peopleData.items.some(item => item.id === '100')).toBe(true);
    expect(result.current.shiftTypeData.items.some(item => item.id === '300')).toBe(true);

    const requirementPref = result.current.preferences.find(pref => pref.type === SHIFT_TYPE_REQUIREMENT) as
      | { date?: string[]; shiftType: string[]; qualifiedPeople: string[] }
      | undefined;
    const successionsPref = result.current.preferences.find(pref => pref.type === SHIFT_TYPE_SUCCESSIONS) as
      | { date?: string[]; person: string[]; pattern: string[] }
      | undefined;
    const requestPref = result.current.preferences.find(pref => pref.type === SHIFT_REQUEST) as
      | { date: string[]; person: string[]; shiftType: string[]; weight: number }
      | undefined;

    expect(requirementPref?.date).toEqual([ALL]);
    expect(requirementPref?.shiftType).toEqual(['300']);
    expect(requirementPref?.qualifiedPeople).toEqual(['100']);
    expect(successionsPref?.date).toEqual([ALL]);
    expect(successionsPref?.person).toEqual(['100']);
    expect(successionsPref?.pattern).toEqual(['300', OFF]);
    expect(requestPref?.date).toEqual(['01']);
    expect(requestPref?.weight).toBe(Infinity);

    const storedRaw = localStorage.getItem(STORAGE_KEY);
    expect(storedRaw).toContain('__INFINITY__');

    unmount();

    const { result: reloadedResult } = renderHook(() => useSchedulingData());
    await waitFor(() => {
      const reloadedRequest = reloadedResult.current.preferences.find(pref => pref.type === SHIFT_REQUEST) as
        | { weight: number }
        | undefined;
      expect(reloadedRequest?.weight).toBe(Infinity);
    });
  });

  it('replaces stale people and shift-type metadata when loading sparse YAML sections', async () => {
    const { result } = renderHook(() => useSchedulingData());

    act(() => {
      result.current.loadFromYaml({
        apiVersion: 'alpha',
        people: {
          items: [{ id: 'Alice', description: 'Existing description', history: ['D'] }],
          groups: [{ id: 'Team A', members: ['Alice'], description: 'Existing group' }],
          history: [],
        },
        shiftTypes: {
          items: [{ id: 'D', description: 'Day' }],
          groups: [{ id: 'Day', members: ['D'], description: 'Existing shift group' }],
        },
      });
    });

    act(() => {
      result.current.loadFromYaml({
        apiVersion: 'alpha',
        people: {
          items: [{ id: 'Alice', description: '', history: [] }],
        },
        shiftTypes: {
          items: [{ id: 'N', description: '' }],
        },
      });
    });

    await waitFor(() => {
      expect(result.current.peopleData.items).toEqual([{ id: 'Alice', description: '', history: [] }]);
      expect(result.current.peopleData.groups).toEqual([expect.objectContaining({ id: 'ALL', members: ['Alice'] })]);
      expect(result.current.shiftTypeData.items).toEqual(
        expect.arrayContaining([
          { id: 'N', description: '' },
          expect.objectContaining({ id: 'OFF', description: 'Off shift type', isAutoGenerated: true }),
        ]),
      );
      expect(result.current.shiftTypeData.groups).toEqual([
        expect.objectContaining({ id: 'ALL', members: ['N'] }),
      ]);
    });
  });

  it('sorts SHIFT_REQUEST preferences and date arrays in updatePreferencesByType', async () => {
    const { result } = renderHook(() => useSchedulingData());

    act(() => {
      result.current.updateDateRange({
        startDate: new Date(Date.UTC(2026, 2, 1, 12)),
        endDate: new Date(Date.UTC(2026, 2, 3, 12)),
      });
    });

    await waitFor(() => {
      expect(result.current.dateData.items.map(item => item.id)).toEqual(['01', '02', '03']);
    });

    act(() => {
      result.current.updatePreferencesByType(SHIFT_REQUEST, [
        {
          type: SHIFT_REQUEST,
          person: ['Person 2'],
          date: ['03', '01'],
          shiftType: ['N'],
          weight: 10,
        },
        {
          type: SHIFT_REQUEST,
          person: ['Person 1'],
          date: ['02', '01'],
          shiftType: ['D'],
          weight: 5,
        },
        {
          type: SHIFT_REQUEST,
          person: ['Person 1'],
          date: ['03', '02'],
          shiftType: ['D'],
          weight: 1,
        },
      ]);
    });

    await waitFor(() => {
      const requests = result.current.preferences.filter(pref => pref.type === SHIFT_REQUEST) as Array<{
        person: string[];
        shiftType: string[];
        date: string[];
        weight: number;
      }>;
      expect(requests).toHaveLength(3);
      expect(requests.map(req => [req.person[0], req.shiftType[0], req.weight])).toEqual([
        ['Person 1', 'D', 1],
        ['Person 1', 'D', 5],
        ['Person 2', 'N', 10],
      ]);
      expect(requests[0].date).toEqual(['02', '03']);
      expect(requests[1].date).toEqual(['01', '02']);
      expect(requests[2].date).toEqual(['01', '03']);
    });
  });

  it('blocks reserved keyword mutations for people items/groups', async () => {
    const { result } = renderHook(() => useSchedulingData());
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined);

    const initialItemCount = result.current.peopleData.items.length;
    const initialGroupCount = result.current.peopleData.groups.length;

    act(() => {
      result.current.addItem(DataType.PEOPLE, result.current.peopleData, ALL, [], '');
      result.current.deleteGroup(DataType.PEOPLE, result.current.peopleData, ALL);
    });

    await waitFor(() => {
      expect(result.current.peopleData.items.length).toBe(initialItemCount);
      expect(result.current.peopleData.groups.length).toBe(initialGroupCount);
    });

    expect(errorSpy).toHaveBeenCalled();
  });

  it('deleting a person cascades and removes invalid dependent preferences', async () => {
    const { result } = renderHook(() => useSchedulingData());

    act(() => {
      result.current.loadFromYaml({
        apiVersion: 'alpha',
        description: 'cascade test',
        dates: {
          range: { startDate: '2026-05-01', endDate: '2026-05-01' },
          items: [{ id: '01', description: 'Date 1' }],
          groups: [],
        },
        people: {
          items: [
            { id: 'P1', description: '', history: [] },
            { id: 'P2', description: '', history: [] },
          ],
          groups: [],
          history: [],
        },
        shiftTypes: {
          items: [{ id: 'D', description: 'Day' }],
          groups: [],
        },
        preferences: [
          { type: SHIFT_REQUEST, person: ['P1'], date: ['01'], shiftType: ['D'], weight: 1 },
          {
            type: SHIFT_COUNT,
            person: ['P1'],
            countDates: ['01'],
            countShiftTypes: ['D'],
            expression: 'x >= T',
            target: 1,
            weight: 2,
          },
          {
            type: SHIFT_AFFINITY,
            date: ['01'],
            people1: ['P1'],
            people2: ['P2'],
            shiftTypes: ['D'],
            weight: 3,
          },
        ],
        export: { formatting: [] },
      });
    });

    await waitFor(() => {
      expect(result.current.peopleData.items.some(item => item.id === 'P1')).toBe(true);
      expect(result.current.preferences.length).toBeGreaterThan(1);
    });

    act(() => {
      result.current.deleteItem(DataType.PEOPLE, result.current.peopleData, 'P1');
    });

    await waitFor(() => {
      expect(result.current.peopleData.items.some(item => item.id === 'P1')).toBe(false);
      expect(result.current.preferences.some(pref => pref.type === SHIFT_REQUEST)).toBe(false);
      expect(result.current.preferences.some(pref => pref.type === SHIFT_COUNT)).toBe(false);
      expect(result.current.preferences.some(pref => pref.type === SHIFT_AFFINITY)).toBe(false);
    });
  });

  it('handles keyboard shortcuts for undo and redo', async () => {
    const { result } = renderHook(() => useSchedulingData());

    act(() => {
      result.current.addPersonHistory('Person 1', 'D');
    });

    await waitFor(() => {
      const person = result.current.peopleData.items.find(item => item.id === 'Person 1');
      expect(person?.history).toEqual(['D']);
    });

    act(() => {
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'z', ctrlKey: true, bubbles: true }));
    });

    await waitFor(() => {
      const person = result.current.peopleData.items.find(item => item.id === 'Person 1');
      expect(person?.history).toEqual([]);
    });

    act(() => {
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'y', ctrlKey: true, bubbles: true }));
    });

    await waitFor(() => {
      const person = result.current.peopleData.items.find(item => item.id === 'Person 1');
      expect(person?.history).toEqual(['D']);
    });
  });

  it('propagates people ID renames across all preference types via updateItem and updateGroup', async () => {
    const { result } = renderHook(() => useSchedulingData());

    act(() => {
      result.current.loadFromYaml({
        apiVersion: 'alpha',
        description: 'rename propagation',
        dates: {
          range: { startDate: '2026-06-01', endDate: '2026-06-01' },
          items: [{ id: '01', description: 'Date 1' }],
          groups: [],
        },
        people: {
          items: [
            { id: 'P1', description: '', history: [] },
            { id: 'P2', description: '', history: [] },
          ],
          groups: [{ id: 'G1', members: ['P1'], description: '' }],
          history: [],
        },
        shiftTypes: {
          items: [{ id: 'D', description: 'Day' }],
          groups: [],
        },
        preferences: [
          {
            type: SHIFT_TYPE_REQUIREMENT,
            shiftType: ['D'],
            requiredNumPeople: 1,
            qualifiedPeople: ['P1', 'G1'],
            date: ['01'],
            weight: 1,
          },
          { type: SHIFT_REQUEST, person: ['G1'], date: ['01'], shiftType: ['D'], weight: 2 },
          { type: SHIFT_TYPE_SUCCESSIONS, person: ['P1'], pattern: ['D'], date: ['01'], weight: 3 },
          {
            type: SHIFT_COUNT,
            person: ['G1'],
            countDates: ['01'],
            countShiftTypes: ['D'],
            expression: 'x >= T',
            target: 1,
            weight: 4,
          },
          {
            type: SHIFT_AFFINITY,
            date: ['01'],
            people1: ['P1'],
            people2: ['G1'],
            shiftTypes: ['D'],
            weight: 5,
          },
        ],
        export: { formatting: [] },
      });
    });

    await waitFor(() => {
      expect(result.current.peopleData.items.some(item => item.id === 'P1')).toBe(true);
      expect(result.current.peopleData.groups.some(group => group.id === 'G1')).toBe(true);
    });

    act(() => {
      result.current.updateItem(DataType.PEOPLE, result.current.peopleData, 'P1', 'P1X');
    });

    await waitFor(() => {
      expect(result.current.peopleData.items.some(item => item.id === 'P1X')).toBe(true);
    });

    act(() => {
      result.current.updateGroup(DataType.PEOPLE, result.current.peopleData, 'G1', 'G1X');
    });

    await waitFor(() => {
      const requirement = result.current.preferences.find(pref => pref.type === SHIFT_TYPE_REQUIREMENT) as
        | { qualifiedPeople: string[] }
        | undefined;
      const request = result.current.preferences.find(pref => pref.type === SHIFT_REQUEST) as
        | { person: string[] }
        | undefined;
      const successions = result.current.preferences.find(pref => pref.type === SHIFT_TYPE_SUCCESSIONS) as
        | { person: string[] }
        | undefined;
      const count = result.current.preferences.find(pref => pref.type === SHIFT_COUNT) as
        | { person: string[] }
        | undefined;
      const affinity = result.current.preferences.find(pref => pref.type === SHIFT_AFFINITY) as
        | { people1: string[]; people2: string[] }
        | undefined;

      expect(requirement?.qualifiedPeople).toEqual(['P1X', 'G1X']);
      expect(request?.person).toEqual(['G1X']);
      expect(successions?.person).toEqual(['P1X']);
      expect(count?.person).toEqual(['G1X']);
      expect(affinity?.people1).toEqual(['P1X']);
      expect(affinity?.people2).toEqual(['G1X']);
    });
  });

  it('logs and ignores out-of-bounds updatePersonHistory operations', async () => {
    const { result } = renderHook(() => useSchedulingData());
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined);

    act(() => {
      result.current.updatePersonHistory('Person 1', 5, 'N');
    });

    await waitFor(() => {
      const person = result.current.peopleData.items.find(item => item.id === 'Person 1');
      expect(person?.history).toEqual([]);
    });

    expect(errorSpy).toHaveBeenCalled();
  });

  it('caps history length to MAX_HISTORY_SIZE through repeated updates', async () => {
    const { result } = renderHook(() => useSchedulingData());

    act(() => {
      for (let i = 0; i < 60; i++) {
        result.current.addPersonHistory('Person 1', 'D');
      }
    });

    await waitFor(() => {
      const person = result.current.peopleData.items.find(item => item.id === 'Person 1');
      expect(person?.history?.length).toBe(60);
    });

    const storedRaw = localStorage.getItem(STORAGE_KEY);
    expect(storedRaw).not.toBeNull();
    const saved = JSON.parse(storedRaw!);
    expect(saved.history.length).toBeLessThanOrEqual(50);
    expect(saved.currentHistoryIndex).toBe(saved.history.length - 1);
  });

  it('keeps state unchanged when undo/redo are called at boundaries', async () => {
    const { result } = renderHook(() => useSchedulingData());

    // At initial boundary: undo should be a no-op.
    act(() => {
      result.current.undo();
    });

    await waitFor(() => {
      const person = result.current.peopleData.items.find(item => item.id === 'Person 1');
      expect(person?.history).toEqual([]);
    });

    // Move to non-empty state then test both end boundaries.
    act(() => {
      result.current.addPersonHistory('Person 1', 'D');
    });

    await waitFor(() => {
      const person = result.current.peopleData.items.find(item => item.id === 'Person 1');
      expect(person?.history).toEqual(['D']);
    });

    // At latest boundary: redo should be a no-op.
    act(() => {
      result.current.redo();
    });

    await waitFor(() => {
      const person = result.current.peopleData.items.find(item => item.id === 'Person 1');
      expect(person?.history).toEqual(['D']);
    });

    // Go back once, then beyond lower boundary.
    act(() => {
      result.current.undo();
    });

    await waitFor(() => {
      const person = result.current.peopleData.items.find(item => item.id === 'Person 1');
      expect(person?.history).toEqual([]);
    });
  });

  it('logs and skips invalid SHIFT_REQUEST entries with empty date arrays', async () => {
    const { result } = renderHook(() => useSchedulingData());
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined);

    act(() => {
      result.current.updateDateRange({
        startDate: new Date(Date.UTC(2026, 7, 1, 12)),
        endDate: new Date(Date.UTC(2026, 7, 2, 12)),
      });
    });

    await waitFor(() => {
      expect(result.current.dateData.items.map(item => item.id)).toEqual(['01', '02']);
    });

    act(() => {
      result.current.updatePreferencesByType(SHIFT_REQUEST, [
        {
          type: SHIFT_REQUEST,
          person: ['Person 1'],
          date: [],
          shiftType: ['D'],
          weight: 1,
        },
      ]);
    });

    await waitFor(() => {
      const requests = result.current.preferences.filter(pref => pref.type === SHIFT_REQUEST) as Array<{ date: string[] }>;
      expect(requests).toHaveLength(1);
      expect(requests[0].date).toEqual([]);
    });

    expect(errorSpy).toHaveBeenCalled();
  });

  it('allows updateExportFormatting to clear formatting with undefined', async () => {
    const { result } = renderHook(() => useSchedulingData());

    act(() => {
      result.current.updateExportFormatting([
        {
          type: 'row',
          people: ['Person 1'],
          backgroundColor: '#ffffff',
        },
      ]);
    });

    await waitFor(() => {
      expect(result.current.exportData.formatting).toHaveLength(1);
    });

    act(() => {
      result.current.updateExportFormatting(undefined);
    });

    await waitFor(() => {
      expect(result.current.exportData.formatting).toBeUndefined();
    });
  });

  it('replaces existing export formatting when YAML omits the export section', async () => {
    const { result } = renderHook(() => useSchedulingData());

    act(() => {
      result.current.updateExportFormatting([
        {
          type: 'row',
          people: ['Person 1'],
          backgroundColor: '#ffffff',
        },
      ]);
    });

    await waitFor(() => {
      expect(result.current.exportData.formatting).toHaveLength(1);
    });

    act(() => {
      result.current.loadFromYaml({
        description: 'yaml without export formatting',
        people: {
          items: [{ id: 'Reloaded Person', description: '', history: [] }],
          groups: [],
          history: [],
        },
      });
    });

    await waitFor(() => {
      expect(result.current.descriptionData).toBe('yaml without export formatting');
      expect(result.current.exportData).toBeUndefined();
    });
  });

  it('logs and skips sorting checks for invalid SHIFT_REQUEST person/shiftType shapes', async () => {
    const { result } = renderHook(() => useSchedulingData());
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined);

    act(() => {
      result.current.updateDateRange({
        startDate: new Date(Date.UTC(2026, 8, 1, 12)),
        endDate: new Date(Date.UTC(2026, 8, 1, 12)),
      });
    });

    await waitFor(() => {
      expect(result.current.dateData.items.map(item => item.id)).toEqual(['01']);
    });

    act(() => {
      result.current.updatePreferencesByType(SHIFT_REQUEST, [
        {
          type: SHIFT_REQUEST,
          person: ['Person 1', 'Person 2'],
          date: ['01'],
          shiftType: ['D'],
          weight: 1,
        },
        {
          type: SHIFT_REQUEST,
          person: ['Person 1'],
          date: ['01'],
          shiftType: ['D', 'N'],
          weight: 2,
        },
      ]);
    });

    await waitFor(() => {
      const requests = result.current.preferences.filter(pref => pref.type === SHIFT_REQUEST);
      expect(requests).toHaveLength(2);
    });

    expect(errorSpy).toHaveBeenCalled();
  });

  it('clears person history entries before a position when shiftTypeId is undefined', async () => {
    const { result } = renderHook(() => useSchedulingData());

    act(() => {
      result.current.addPersonHistory('Person 1', 'D');
      result.current.addPersonHistory('Person 1', 'N');
      result.current.addPersonHistory('Person 1', 'A');
    });

    await waitFor(() => {
      const person = result.current.peopleData.items.find(item => item.id === 'Person 1');
      expect(person?.history).toEqual(['A', 'N', 'D']);
    });

    act(() => {
      result.current.updatePersonHistory('Person 1', 1);
    });

    await waitFor(() => {
      const person = result.current.peopleData.items.find(item => item.id === 'Person 1');
      expect(person?.history).toEqual(['D']);
    });
  });

  it('keeps state unchanged when person history is updated for unknown person IDs', async () => {
    const { result } = renderHook(() => useSchedulingData());

    const getPerson1History = () =>
      result.current.peopleData.items.find(item => item.id === 'Person 1')?.history ?? [];

    expect(getPerson1History()).toEqual([]);

    act(() => {
      result.current.addPersonHistory('UNKNOWN_PERSON', 'D');
      result.current.updatePersonHistory('UNKNOWN_PERSON', 0, 'N');
      result.current.updatePersonHistory('UNKNOWN_PERSON', 0);
    });

    await waitFor(() => {
      expect(getPerson1History()).toEqual([]);
    });
  });

  it('filters by preference type and supports direct preference replacement', async () => {
    const { result } = renderHook(() => useSchedulingData());

    act(() => {
      result.current.updatePreferences([
        { type: 'at most one shift per day' },
        {
          type: SHIFT_REQUEST,
          person: ['Person 1'],
          date: ['01'],
          shiftType: ['D'],
          weight: 3,
        },
        {
          type: SHIFT_COUNT,
          person: ['Person 1'],
          countDates: ['01'],
          countShiftTypes: ['D'],
          expression: 'x >= T',
          target: 1,
          weight: 5,
        },
      ]);
    });

    await waitFor(() => {
      expect(result.current.preferences).toHaveLength(3);
    });

    const shiftRequests = result.current.getPreferencesByType<{
      type: string;
      person: string[];
      weight: number;
    }>(SHIFT_REQUEST);
    const shiftCounts = result.current.getPreferencesByType<{ type: string; weight: number }>(SHIFT_COUNT);

    expect(shiftRequests).toHaveLength(1);
    expect(shiftRequests[0].person).toEqual(['Person 1']);
    expect(shiftRequests[0].weight).toBe(3);
    expect(shiftCounts).toHaveLength(1);
    expect(shiftCounts[0].weight).toBe(5);
  });

  it('resets to defaults via createNewState after mutations', async () => {
    const { result } = renderHook(() => useSchedulingData());

    act(() => {
      result.current.updatePreferences([
        {
          type: SHIFT_REQUEST,
          person: ['Person 1'],
          date: ['01'],
          shiftType: ['D'],
          weight: 99,
        },
      ]);
      result.current.addPersonHistory('Person 1', 'N');
    });

    await waitFor(() => {
      expect(result.current.preferences.some(pref => pref.type === SHIFT_REQUEST)).toBe(true);
      const person = result.current.peopleData.items.find(item => item.id === 'Person 1');
      expect(person?.history).toEqual(['N']);
    });

    act(() => {
      result.current.createNewState();
    });

    await waitFor(() => {
      expect(result.current.preferences.some(pref => pref.type === SHIFT_REQUEST)).toBe(false);
      const person = result.current.peopleData.items.find(item => item.id === 'Person 1');
      expect(person?.history).toEqual([]);
      expect(result.current.preferences[0].type).toBe('at most one shift per day');
    });
  });

  it('undoes and redoes across a loadFromYaml to createNewState boundary', async () => {
    const { result } = renderHook(() => useSchedulingData());

    act(() => {
      result.current.loadFromYaml({
        apiVersion: 'alpha',
        description: 'loaded state',
        people: {
          items: [{ id: 'Uploaded Person', description: '', history: [] }],
          groups: [],
          history: [],
        },
        shiftTypes: { items: [{ id: 'X', description: 'Extra' }], groups: [] },
        preferences: [{ type: SHIFT_REQUEST, person: ['Uploaded Person'], date: ['ALL'], shiftType: ['X'], weight: 1 }],
        export: { formatting: [] },
      });
    });

    await waitFor(() => {
      expect(result.current.descriptionData).toBe('loaded state');
      expect(result.current.peopleData.items.some(item => item.id === 'Uploaded Person')).toBe(true);
    });

    act(() => {
      result.current.createNewState();
    });

    await waitFor(() => {
      expect(result.current.descriptionData).toBe('');
      expect(result.current.peopleData.items.some(item => item.id === 'Uploaded Person')).toBe(false);
      expect(result.current.peopleData.items.some(item => item.id === 'Person 1')).toBe(true);
    });

    act(() => {
      result.current.undo();
    });

    await waitFor(() => {
      expect(result.current.descriptionData).toBe('loaded state');
      expect(result.current.peopleData.items.some(item => item.id === 'Uploaded Person')).toBe(true);
    });

    act(() => {
      result.current.redo();
    });

    await waitFor(() => {
      expect(result.current.descriptionData).toBe('');
      expect(result.current.peopleData.items.some(item => item.id === 'Uploaded Person')).toBe(false);
    });
  });

  it('reorders people groups and preserves the new order', async () => {
    const { result } = renderHook(() => useSchedulingData());

    const originalGroups = result.current.peopleData.groups;
    expect(originalGroups.length).toBeGreaterThan(1);

    const reordered = [...originalGroups].reverse();

    act(() => {
      result.current.reorderGroups(DataType.PEOPLE, result.current.peopleData, reordered);
    });

    await waitFor(() => {
      const nonAutoGroupIds = result.current.peopleData.groups.filter(group => !group.isAutoGenerated).map(group => group.id);
      const expectedNonAutoGroupIds = reordered.filter(group => !group.isAutoGenerated).map(group => group.id);
      expect(nonAutoGroupIds).toEqual(expectedNonAutoGroupIds);
      expect(result.current.peopleData.groups.some(group => group.id === ALL)).toBe(true);
    });
  });

  it('deleting a people group cascades and removes dependent group-based preferences', async () => {
    const { result } = renderHook(() => useSchedulingData());

    act(() => {
      result.current.loadFromYaml({
        apiVersion: 'alpha',
        description: 'group cascade',
        dates: {
          range: { startDate: '2026-10-01', endDate: '2026-10-01' },
          items: [{ id: '01', description: 'Date 1' }],
          groups: [],
        },
        people: {
          items: [{ id: 'P1', description: '', history: [] }],
          groups: [{ id: 'G1', members: ['P1'], description: '' }],
          history: [],
        },
        shiftTypes: {
          items: [{ id: 'D', description: 'Day' }],
          groups: [],
        },
        preferences: [
          { type: SHIFT_REQUEST, person: ['G1'], date: ['01'], shiftType: ['D'], weight: 1 },
          {
            type: SHIFT_COUNT,
            person: ['G1'],
            countDates: ['01'],
            countShiftTypes: ['D'],
            expression: 'x >= T',
            target: 1,
            weight: 2,
          },
          {
            type: SHIFT_AFFINITY,
            date: ['01'],
            people1: ['G1'],
            people2: ['P1'],
            shiftTypes: ['D'],
            weight: 3,
          },
        ],
        export: { formatting: [] },
      });
    });

    await waitFor(() => {
      expect(result.current.peopleData.groups.some(group => group.id === 'G1')).toBe(true);
      expect(result.current.preferences.length).toBeGreaterThan(0);
    });

    act(() => {
      result.current.deleteGroup(DataType.PEOPLE, result.current.peopleData, 'G1');
    });

    await waitFor(() => {
      expect(result.current.peopleData.groups.some(group => group.id === 'G1')).toBe(false);
      expect(result.current.preferences.some(pref => pref.type === SHIFT_REQUEST)).toBe(false);
      expect(result.current.preferences.some(pref => pref.type === SHIFT_COUNT)).toBe(false);
      expect(result.current.preferences.some(pref => pref.type === SHIFT_AFFINITY)).toBe(false);
    });
  });

  it('undoes and redoes grouped delete cascades across dependent preferences', async () => {
    const { result } = renderHook(() => useSchedulingData());

    act(() => {
      result.current.loadFromYaml({
        apiVersion: 'alpha',
        description: 'group cascade undo redo',
        dates: {
          range: { startDate: '2026-10-01', endDate: '2026-10-01' },
          items: [{ id: '01', description: 'Date 1' }],
          groups: [{ id: 'DATES_G', members: ['01'], description: '' }],
        },
        people: {
          items: [{ id: 'P1', description: '', history: [] }, { id: 'P2', description: '', history: [] }],
          groups: [{ id: 'G1', members: ['P1', 'P2'], description: '' }],
          history: [],
        },
        shiftTypes: {
          items: [{ id: 'D', description: 'Day' }],
          groups: [{ id: 'SHIFT_G', members: ['D'], description: '' }],
        },
        preferences: [
          { type: SHIFT_REQUEST, person: ['G1'], date: ['DATES_G'], shiftType: ['SHIFT_G'], weight: 1 },
          { type: SHIFT_TYPE_SUCCESSIONS, person: ['G1'], pattern: ['SHIFT_G'], weight: 2 },
          {
            type: SHIFT_COUNT,
            person: ['G1'],
            countDates: ['DATES_G'],
            countShiftTypes: ['SHIFT_G'],
            expression: 'x >= T',
            target: 1,
            weight: 3,
          },
          {
            type: SHIFT_AFFINITY,
            date: ['DATES_G'],
            people1: ['G1'],
            people2: ['P2'],
            shiftTypes: ['SHIFT_G'],
            weight: 4,
          },
        ],
        export: { formatting: [] },
      });
    });

    act(() => {
      result.current.deleteGroup(DataType.PEOPLE, result.current.peopleData, 'G1');
    });

    await waitFor(() => {
      expect(result.current.peopleData.groups.some(group => group.id === 'G1')).toBe(false);
      expect(result.current.preferences.some(pref => JSON.stringify(pref).includes('"G1"'))).toBe(false);
    });

    act(() => {
      result.current.undo();
    });

    await waitFor(() => {
      expect(result.current.peopleData.groups.some(group => group.id === 'G1')).toBe(true);
      expect(result.current.preferences.some(pref => JSON.stringify(pref).includes('"G1"'))).toBe(true);
    });

    act(() => {
      result.current.redo();
    });

    await waitFor(() => {
      expect(result.current.peopleData.groups.some(group => group.id === 'G1')).toBe(false);
      expect(result.current.preferences.some(pref => JSON.stringify(pref).includes('"G1"'))).toBe(false);
    });
  });

  it('reorders items and keeps each group member order aligned to item order', async () => {
    const { result } = renderHook(() => useSchedulingData());

    const reversedItems = [...result.current.peopleData.items].reverse();
    const group1Before = result.current.peopleData.groups.find(group => group.id === 'Group 1');
    expect(group1Before?.members).toEqual(['Person 1', 'Person 2']);

    act(() => {
      result.current.reorderItems(DataType.PEOPLE, result.current.peopleData, reversedItems);
    });

    await waitFor(() => {
      const group1After = result.current.peopleData.groups.find(group => group.id === 'Group 1');
      expect(group1After?.members).toEqual(['Person 2', 'Person 1']);
      expect(group1After?.members.every(id => reversedItems.some(item => item.id === id))).toBe(true);
    });
  });

  it('renaming/deleting shift types cascades to preferences and people history', async () => {
    const { result } = renderHook(() => useSchedulingData());

    act(() => {
      result.current.loadFromYaml({
        apiVersion: 'alpha',
        description: 'shift-type cascade',
        dates: {
          range: { startDate: '2026-11-01', endDate: '2026-11-01' },
          items: [{ id: '01', description: 'Date 1' }],
          groups: [],
        },
        people: {
          items: [{ id: 'P1', description: '', history: ['D'] }],
          groups: [],
          history: [],
        },
        shiftTypes: {
          items: [{ id: 'D', description: 'Day' }],
          groups: [],
        },
        preferences: [
          {
            type: SHIFT_TYPE_REQUIREMENT,
            shiftType: ['D'],
            requiredNumPeople: 1,
            qualifiedPeople: ['P1'],
            date: ['01'],
            weight: 1,
          },
          { type: SHIFT_REQUEST, person: ['P1'], date: ['01'], shiftType: ['D'], weight: 2 },
          { type: SHIFT_TYPE_SUCCESSIONS, person: ['P1'], pattern: ['D'], date: ['01'], weight: 3 },
          {
            type: SHIFT_COUNT,
            person: ['P1'],
            countDates: ['01'],
            countShiftTypes: ['D'],
            expression: 'x >= T',
            target: 1,
            weight: 4,
          },
          {
            type: SHIFT_AFFINITY,
            date: ['01'],
            people1: ['P1'],
            people2: ['P1'],
            shiftTypes: ['D'],
            weight: 5,
          },
        ],
        export: { formatting: [] },
      });
    });

    await waitFor(() => {
      expect(result.current.shiftTypeData.items.some(item => item.id === 'D')).toBe(true);
    });

    act(() => {
      result.current.updateItem(DataType.SHIFT_TYPES, result.current.shiftTypeData, 'D', 'DX');
    });

    await waitFor(() => {
      const person = result.current.peopleData.items.find(item => item.id === 'P1');
      expect(person?.history).toContain('DX');
      expect(result.current.preferences.some(pref => JSON.stringify(pref).includes('"D"'))).toBe(false);
      expect(result.current.preferences.some(pref => JSON.stringify(pref).includes('"DX"'))).toBe(true);
    });

    act(() => {
      result.current.deleteItem(DataType.SHIFT_TYPES, result.current.shiftTypeData, 'DX');
    });

    await waitFor(() => {
      const person = result.current.peopleData.items.find(item => item.id === 'P1');
      // History renaming is supported, but history deletion is currently not cascaded.
      expect(person?.history).toEqual(['DX']);
      expect(result.current.preferences.some(pref => pref.type === SHIFT_REQUEST)).toBe(false);
      expect(result.current.preferences.some(pref => pref.type === SHIFT_TYPE_REQUIREMENT)).toBe(false);
      expect(result.current.preferences.some(pref => pref.type === SHIFT_TYPE_SUCCESSIONS)).toBe(false);
      expect(result.current.preferences.some(pref => pref.type === SHIFT_COUNT)).toBe(true);
      expect(result.current.preferences.some(pref => pref.type === SHIFT_AFFINITY)).toBe(false);
    });
  });

  it('deleting dates cascades through date-based preferences', async () => {
    const { result } = renderHook(() => useSchedulingData());

    act(() => {
      result.current.loadFromYaml({
        apiVersion: 'alpha',
        description: 'date cascade',
        dates: {
          range: { startDate: '2026-12-01', endDate: '2026-12-01' },
          items: [{ id: '01', description: 'Date 1' }],
          groups: [],
        },
        people: {
          items: [{ id: 'P1', description: '', history: [] }],
          groups: [],
          history: [],
        },
        shiftTypes: {
          items: [{ id: 'D', description: 'Day' }],
          groups: [],
        },
        preferences: [
          {
            type: SHIFT_TYPE_REQUIREMENT,
            shiftType: ['D'],
            requiredNumPeople: 1,
            qualifiedPeople: ['P1'],
            date: ['01'],
            weight: 1,
          },
          { type: SHIFT_REQUEST, person: ['P1'], date: ['01'], shiftType: ['D'], weight: 2 },
          { type: SHIFT_TYPE_SUCCESSIONS, person: ['P1'], pattern: ['D'], date: ['01'], weight: 3 },
          {
            type: SHIFT_COUNT,
            person: ['P1'],
            countDates: ['01'],
            countShiftTypes: ['D'],
            expression: 'x >= T',
            target: 1,
            weight: 4,
          },
          {
            type: SHIFT_AFFINITY,
            date: ['01'],
            people1: ['P1'],
            people2: ['P1'],
            shiftTypes: ['D'],
            weight: 5,
          },
        ],
        export: { formatting: [] },
      });
    });

    act(() => {
      result.current.deleteItem(DataType.DATES, result.current.dateData, '01');
    });

    await waitFor(() => {
      expect(result.current.preferences.some(pref => pref.type === SHIFT_REQUEST)).toBe(false);
      expect(result.current.preferences.some(pref => pref.type === SHIFT_TYPE_REQUIREMENT)).toBe(true);
      expect(result.current.preferences.some(pref => pref.type === SHIFT_COUNT)).toBe(true);
      expect(result.current.preferences.some(pref => pref.type === SHIFT_AFFINITY)).toBe(false);
      expect(result.current.preferences.some(pref => pref.type === SHIFT_TYPE_SUCCESSIONS)).toBe(true);
    });
  });

  it('blocks reserved-keyword mutations for update item/group and remove-from-group across data types', async () => {
    const { result } = renderHook(() => useSchedulingData());
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined);

    act(() => {
      result.current.updateDateRange({
        startDate: new Date(Date.UTC(2026, 0, 1, 12)),
        endDate: new Date(Date.UTC(2026, 0, 1, 12)),
      });
    });

    await waitFor(() => {
      expect(result.current.dateData.groups.some(group => group.id === ALL)).toBe(true);
    });

    const beforePeople = result.current.peopleData;
    const beforeShiftTypes = result.current.shiftTypeData;
    const beforeDates = result.current.dateData;

    act(() => {
      result.current.updateItem(DataType.PEOPLE, result.current.peopleData, 'Person 1', ALL);
      result.current.updateGroup(DataType.PEOPLE, result.current.peopleData, 'Group 1', ALL);
      result.current.removeItemFromGroup(DataType.PEOPLE, result.current.peopleData, 'Person 1', ALL);

      result.current.updateItem(DataType.SHIFT_TYPES, result.current.shiftTypeData, 'D', OFF);
      result.current.updateGroup(DataType.SHIFT_TYPES, result.current.shiftTypeData, ALL, OFF);
      result.current.removeItemFromGroup(DataType.SHIFT_TYPES, result.current.shiftTypeData, 'D', ALL);

      result.current.updateItem(DataType.DATES, result.current.dateData, '01', ALL);
      result.current.updateGroup(DataType.DATES, result.current.dateData, ALL, ALL);
      result.current.removeItemFromGroup(DataType.DATES, result.current.dateData, '01', ALL);
    });

    await waitFor(() => {
      expect(result.current.peopleData.items[0].id).toBe(beforePeople.items[0].id);
      expect(result.current.shiftTypeData.items.some(item => item.id === 'D')).toBe(
        beforeShiftTypes.items.some(item => item.id === 'D'),
      );
      expect(result.current.dateData.items.some(item => item.id === '01')).toBe(
        beforeDates.items.some(item => item.id === '01'),
      );
    });

    expect(errorSpy).toHaveBeenCalled();
  });

  it('removes item membership from a non-reserved group', async () => {
    const { result } = renderHook(() => useSchedulingData());

    const beforeGroup = result.current.peopleData.groups.find(group => group.id === 'Group 1');
    expect(beforeGroup?.members).toContain('Person 1');

    act(() => {
      result.current.removeItemFromGroup(DataType.PEOPLE, result.current.peopleData, 'Person 1', 'Group 1');
    });

    await waitFor(() => {
      const afterGroup = result.current.peopleData.groups.find(group => group.id === 'Group 1');
      expect(afterGroup?.members).not.toContain('Person 1');
    });
  });

  it('leaves state unchanged when removing an item from a group it is not part of', async () => {
    const { result } = renderHook(() => useSchedulingData());

    const beforeGroup1 = result.current.peopleData.groups.find(group => group.id === 'Group 1');
    const beforeGroup2 = result.current.peopleData.groups.find(group => group.id === 'Group 2');

    act(() => {
      result.current.removeItemFromGroup(DataType.PEOPLE, result.current.peopleData, 'Person 10', 'Group 1');
    });

    await waitFor(() => {
      const afterGroup1 = result.current.peopleData.groups.find(group => group.id === 'Group 1');
      const afterGroup2 = result.current.peopleData.groups.find(group => group.id === 'Group 2');
      expect(afterGroup1?.members).toEqual(beforeGroup1?.members);
      expect(afterGroup2?.members).toEqual(beforeGroup2?.members);
    });
  });

  it('logs and no-ops when updateItem would create inconsistent group members', async () => {
    const { result } = renderHook(() => useSchedulingData());
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined);

    act(() => {
      result.current.loadFromYaml({
        apiVersion: 'alpha',
        description: 'inconsistent members',
        dates: { range: { startDate: '2026-01-01', endDate: '2026-01-01' }, items: [{ id: '01', description: '' }], groups: [] },
        people: {
          items: [{ id: 'P1', description: '', history: [] }],
          groups: [{ id: 'G1', members: ['P1', 'MISSING'], description: '' }],
          history: [],
        },
        shiftTypes: { items: [{ id: 'D', description: '' }], groups: [] },
        preferences: [],
        export: { formatting: [] },
      });
    });

    act(() => {
      result.current.updateItem(DataType.PEOPLE, result.current.peopleData, 'P1', 'P1X');
    });

    await waitFor(() => {
      const group = result.current.peopleData.groups.find(g => g.id === 'G1');
      expect(group?.members).toEqual(['P1', 'MISSING']);
    });
    expect(errorSpy).toHaveBeenCalled();
  });

  it('logs and no-ops when updateGroup receives members not present in items', async () => {
    const { result } = renderHook(() => useSchedulingData());
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined);

    act(() => {
      result.current.updateGroup(DataType.PEOPLE, result.current.peopleData, 'Group 1', 'Group 1X', ['Person 1', 'Ghost']);
    });

    await waitFor(() => {
      expect(result.current.peopleData.groups.some(group => group.id === 'Group 1X')).toBe(false);
      expect(result.current.peopleData.groups.some(group => group.id === 'Group 1')).toBe(true);
    });
    expect(errorSpy).toHaveBeenCalled();
  });

  it('updates person history at a valid index when shiftTypeId is provided', async () => {
    const { result } = renderHook(() => useSchedulingData());

    act(() => {
      result.current.addPersonHistory('Person 1', 'D');
      result.current.addPersonHistory('Person 1', 'N');
    });

    await waitFor(() => {
      const person = result.current.peopleData.items.find(item => item.id === 'Person 1');
      expect(person?.history).toEqual(['N', 'D']);
    });

    act(() => {
      result.current.updatePersonHistory('Person 1', 1, 'A');
    });

    await waitFor(() => {
      const person = result.current.peopleData.items.find(item => item.id === 'Person 1');
      expect(person?.history).toEqual(['N', 'A']);
    });
  });

  it('keeps preferences unchanged when updateDateRange removes no date IDs', async () => {
    const { result } = renderHook(() => useSchedulingData());

    act(() => {
      result.current.updateDateRange({
        startDate: new Date(Date.UTC(2026, 0, 1, 12)),
        endDate: new Date(Date.UTC(2026, 0, 2, 12)),
      });
    });

    act(() => {
      result.current.updatePreferencesByType(SHIFT_REQUEST, [
        { type: SHIFT_REQUEST, person: ['Person 1'], date: ['01'], shiftType: ['D'], weight: 1 },
      ]);
    });

    await waitFor(() => {
      expect(result.current.preferences.filter(pref => pref.type === SHIFT_REQUEST)).toHaveLength(1);
    });

    act(() => {
      result.current.updateDateRange({
        startDate: new Date(Date.UTC(2026, 0, 1, 12)),
        endDate: new Date(Date.UTC(2026, 0, 2, 12)),
      });
    });

    await waitFor(() => {
      expect(result.current.preferences.filter(pref => pref.type === SHIFT_REQUEST)).toHaveLength(1);
    });
  });

  it('keeps memberships and preferences stable for description-only item updates', async () => {
    const { result } = renderHook(() => useSchedulingData());

    act(() => {
      result.current.updatePreferencesByType(SHIFT_REQUEST, [
        { type: SHIFT_REQUEST, person: ['Person 1'], date: ['ALL'], shiftType: ['D'], weight: 1 },
      ]);
    });

    const groupsBefore = result.current.peopleData.groups.map(group => ({
      id: group.id,
      members: [...group.members],
    }));
    const requestsBefore = result.current.preferences.filter(pref => pref.type === SHIFT_REQUEST);

    act(() => {
      result.current.updateItem(
        DataType.PEOPLE,
        result.current.peopleData,
        'Person 1',
        'Person 1',
        undefined,
        'Updated description only',
      );
    });

    await waitFor(() => {
      const person1 = result.current.peopleData.items.find(item => item.id === 'Person 1');
      expect(person1?.description).toBe('Updated description only');
      expect(result.current.peopleData.groups.map(group => ({ id: group.id, members: group.members }))).toEqual(
        groupsBefore,
      );
      expect(result.current.preferences.filter(pref => pref.type === SHIFT_REQUEST)).toEqual(requestsBefore);
    });
  });

  it('keeps group memberships and preference identities intact across chained reorders', async () => {
    const { result } = renderHook(() => useSchedulingData());

    act(() => {
      result.current.updatePreferencesByType(SHIFT_REQUEST, [
        { type: SHIFT_REQUEST, person: ['Person 1'], date: ['ALL'], shiftType: ['D'], weight: 1 },
        { type: SHIFT_REQUEST, person: ['Person 2'], date: ['ALL'], shiftType: ['N'], weight: 2 },
      ]);
    });

    const baselineIds = result.current.peopleData.items.slice(0, 3).map(item => item.id);

    act(() => {
      const reorderedOnce = [
        result.current.peopleData.items[1],
        result.current.peopleData.items[2],
        result.current.peopleData.items[0],
        ...result.current.peopleData.items.slice(3),
      ];
      result.current.reorderItems(DataType.PEOPLE, result.current.peopleData, reorderedOnce);
    });

    act(() => {
      const reorderedTwice = [
        result.current.peopleData.items[2],
        result.current.peopleData.items[0],
        result.current.peopleData.items[1],
        ...result.current.peopleData.items.slice(3),
      ];
      result.current.reorderItems(DataType.PEOPLE, result.current.peopleData, reorderedTwice);
    });

    await waitFor(() => {
      const group1 = result.current.peopleData.groups.find(group => group.id === 'Group 1');
      expect(group1?.members).toEqual(['Person 1', 'Person 2']);
      const requests = result.current.preferences.filter(pref => pref.type === SHIFT_REQUEST) as Array<{ person: string[] }>;
      expect(requests.map(req => req.person[0]).sort()).toEqual(['Person 1', 'Person 2']);
      expect(baselineIds).toEqual(['Person 1', 'Person 2', 'Person 3']);
    });
  });

  it('truncates redo history after loadFromYaml is called from an undone state', async () => {
    const { result } = renderHook(() => useSchedulingData());

    act(() => {
      result.current.addPersonHistory('Person 1', 'D');
      result.current.addPersonHistory('Person 1', 'N');
    });

    await waitFor(() => {
      const person = result.current.peopleData.items.find(item => item.id === 'Person 1');
      expect(person?.history).toEqual(['N', 'D']);
    });

    act(() => {
      result.current.undo();
    });

    await waitFor(() => {
      const person = result.current.peopleData.items.find(item => item.id === 'Person 1');
      expect(person?.history).toEqual(['D']);
    });

    act(() => {
      result.current.loadFromYaml({ description: 'branch replacement' });
    });

    await waitFor(() => {
      expect(result.current.descriptionData).toBe('branch replacement');
    });

    act(() => {
      result.current.redo();
    });

    await waitFor(() => {
      expect(result.current.descriptionData).toBe('branch replacement');
      const person = result.current.peopleData.items.find(item => item.id === 'Person 1');
      expect(person?.history?.[0]).not.toBe('N');
    });
  });

  it('treats loadFromYaml as a single undoable history boundary', async () => {
    const { result } = renderHook(() => useSchedulingData());

    act(() => {
      result.current.addPersonHistory('Person 1', 'D');
    });

    await waitFor(() => {
      expect(result.current.peopleData.items.find(item => item.id === 'Person 1')?.history).toEqual(['D']);
    });

    act(() => {
      result.current.loadFromYaml({
        description: 'loaded replacement',
        people: {
          items: [{ id: 'Uploaded Person', description: '', history: [] }],
          groups: [],
          history: [],
        },
      });
    });

    await waitFor(() => {
      expect(result.current.descriptionData).toBe('loaded replacement');
      expect(result.current.peopleData.items.some(item => item.id === 'Uploaded Person')).toBe(true);
    });

    act(() => {
      result.current.undo();
    });

    await waitFor(() => {
      expect(result.current.descriptionData).toBe('');
      expect(result.current.peopleData.items.find(item => item.id === 'Person 1')?.history).toEqual(['D']);
      expect(result.current.peopleData.items.some(item => item.id === 'Uploaded Person')).toBe(false);
    });

    act(() => {
      result.current.redo();
    });

    await waitFor(() => {
      expect(result.current.descriptionData).toBe('loaded replacement');
      expect(result.current.peopleData.items.some(item => item.id === 'Uploaded Person')).toBe(true);
    });
  });

  it('keeps persisted history length capped with mixed mutators', async () => {
    const { result } = renderHook(() => useSchedulingData());

    for (let i = 0; i < 60; i++) {
      act(() => {
        if (i % 2 === 0) {
          result.current.addPersonHistory('Person 1', 'D');
        } else {
          result.current.updateDateRange({
            startDate: new Date(Date.UTC(2026, 0, 1, 12)),
            endDate: new Date(Date.UTC(2026, 0, 1 + (i % 5), 12)),
          });
        }
      });
    }

    await waitFor(() => {
      const storedRaw = localStorage.getItem(STORAGE_KEY);
      expect(storedRaw).not.toBeNull();
      const parsed = JSON.parse(storedRaw!);
      expect(parsed.history.length).toBeLessThanOrEqual(50);
      expect(parsed.currentHistoryIndex).toBe(parsed.history.length - 1);
    });
  });

  it('falls back to default state when localStorage contains malformed history shape', async () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ state: null, history: 'bad', currentHistoryIndex: 999 }));
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined);

    const { result } = renderHook(() => useSchedulingData());

    await waitFor(() => {
      expect(result.current.peopleData.items.length).toBeGreaterThan(0);
    });

    expect(result.current.descriptionData).toBe('');
    expect(errorSpy).toHaveBeenCalled();
  });

  it('falls back to default state when storage is missing current state and contains malformed history entries', async () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      history: [
        null,
        {
          apiVersion: 'alpha',
          description: 'broken-history-entry',
        },
      ],
      currentHistoryIndex: 5,
    }));
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined);

    const { result } = renderHook(() => useSchedulingData());

    await waitFor(() => {
      expect(result.current.peopleData.items.length).toBeGreaterThan(0);
    });

    expect(result.current.descriptionData).toBe('');
    expect(errorSpy).toHaveBeenCalled();
  });

  it('converts numeric IDs in affinity and count preference shapes during YAML load', async () => {
    const { result } = renderHook(() => useSchedulingData());

    act(() => {
      result.current.loadFromYaml({
        apiVersion: 'alpha',
        people: {
          items: [{ id: 1, description: '', history: [] }, { id: 2, description: '', history: [] }],
          groups: [],
          history: [],
        },
        shiftTypes: {
          items: [{ id: 10, description: '' }, { id: 11, description: '' }],
          groups: [],
        },
        dates: {
          range: { startDate: '2026-04-01', endDate: '2026-04-01' },
          items: [{ id: 1, description: '' }],
          groups: [],
        },
        preferences: [
          {
            type: SHIFT_AFFINITY,
            date: [1],
            people1: [1],
            people2: [2],
            shiftTypes: [10, 11],
            weight: 5,
          },
          {
            type: SHIFT_COUNT,
            person: [1],
            countDates: [1],
            minCount: 0,
            maxCount: 2,
            countShiftTypes: [10, 11],
            weight: 1,
          },
        ],
        export: { formatting: [] },
      });
    });

    await waitFor(() => {
      const affinity = result.current.preferences.find(pref => pref.type === SHIFT_AFFINITY) as
        | { date: string[]; people1: string[]; people2: string[]; shiftTypes: string[] }
        | undefined;
      const count = result.current.preferences.find(pref => pref.type === SHIFT_COUNT) as
        | { person: string[]; countDates: string[]; countShiftTypes: string[] }
        | undefined;

      expect(affinity).toEqual({
        type: SHIFT_AFFINITY,
        date: ['01'],
        people1: ['1'],
        people2: ['2'],
        shiftTypes: ['10', '11'],
        weight: 5,
      });
      expect(count?.person).toEqual(['1']);
      expect(count?.countDates).toEqual(['01']);
      expect(count?.countShiftTypes).toEqual(['10', '11']);
    });
  });

  it('cascades person deletion across multiple preference types in one state blob', async () => {
    const { result } = renderHook(() => useSchedulingData());

    act(() => {
      result.current.loadFromYaml({
        apiVersion: 'alpha',
        dates: {
          range: { startDate: '2026-04-01', endDate: '2026-04-01' },
          items: [{ id: '01', description: '' }],
          groups: [],
        },
        people: {
          items: [
            { id: 'P1', description: '', history: [] },
            { id: 'P2', description: '', history: [] },
          ],
          groups: [],
          history: [],
        },
        shiftTypes: {
          items: [{ id: 'D', description: '' }, { id: 'N', description: '' }],
          groups: [],
        },
        preferences: [
          { type: SHIFT_REQUEST, person: ['P1'], date: ['01'], shiftType: ['D'], weight: 1 },
          { type: SHIFT_TYPE_SUCCESSIONS, person: ['P1'], pattern: ['D', 'N'], weight: 2 },
          { type: SHIFT_COUNT, person: ['P1'], countDates: ['01'], minCount: 0, maxCount: 1, weight: 3 },
          { type: SHIFT_AFFINITY, date: ['01'], people1: ['P1'], people2: ['P2'], shiftTypes: ['D'], weight: 4 },
        ],
        export: { formatting: [] },
      });
    });

    act(() => {
      result.current.deleteItem(DataType.PEOPLE, result.current.peopleData, 'P1');
    });

    await waitFor(() => {
      expect(result.current.peopleData.items.some(item => item.id === 'P1')).toBe(false);
      expect(result.current.preferences.some(pref => pref.type === SHIFT_REQUEST)).toBe(false);
      expect(result.current.preferences.some(pref => pref.type === SHIFT_TYPE_SUCCESSIONS)).toBe(false);
      expect(result.current.preferences.some(pref => pref.type === SHIFT_COUNT)).toBe(false);
      expect(result.current.preferences.some(pref => pref.type === SHIFT_AFFINITY)).toBe(false);
    });
  });

  it('renames a shift type consistently across combined preference shapes in one mutation', async () => {
    const { result } = renderHook(() => useSchedulingData());

    act(() => {
      result.current.loadFromYaml({
        apiVersion: 'alpha',
        dates: {
          range: { startDate: '2026-04-01', endDate: '2026-04-02' },
          items: [{ id: '01', description: '' }, { id: '02', description: '' }],
          groups: [],
        },
        people: {
          items: [
            { id: 'P1', description: '', history: ['D'] },
            { id: 'P2', description: '', history: [] },
          ],
          groups: [{ id: 'G1', members: ['P1', 'P2'], description: '' }],
          history: [],
        },
        shiftTypes: {
          items: [{ id: 'D', description: '' }, { id: 'N', description: '' }],
          groups: [],
        },
        preferences: [
          { type: SHIFT_REQUEST, person: ['G1'], date: ['01'], shiftType: ['D'], weight: 1 },
          {
            type: SHIFT_TYPE_REQUIREMENT,
            date: ['01'],
            shiftType: ['D'],
            qualifiedPeople: ['P1', 'G1'],
            requiredNumPeople: 1,
            weight: 2,
          },
          { type: SHIFT_TYPE_SUCCESSIONS, person: ['P1'], date: ['01'], pattern: ['D', 'N'], weight: 3 },
          {
            type: SHIFT_COUNT,
            person: ['P2'],
            countDates: ['01', '02'],
            countShiftTypes: ['D', 'N'],
            expression: 'x >= T',
            target: 1,
            weight: 4,
          },
          {
            type: SHIFT_AFFINITY,
            date: ['02'],
            people1: ['P1'],
            people2: ['P2'],
            shiftTypes: ['D'],
            weight: 5,
          },
        ],
        export: { formatting: [] },
      });
    });

    act(() => {
      result.current.updateItem(DataType.SHIFT_TYPES, result.current.shiftTypeData, 'D', 'DX');
    });

    await waitFor(() => {
      const request = result.current.preferences.find(pref => pref.type === SHIFT_REQUEST) as
        | { shiftType: string[] }
        | undefined;
      const requirement = result.current.preferences.find(pref => pref.type === SHIFT_TYPE_REQUIREMENT) as
        | { shiftType: string[] }
        | undefined;
      const successions = result.current.preferences.find(pref => pref.type === SHIFT_TYPE_SUCCESSIONS) as
        | { pattern: string[] }
        | undefined;
      const count = result.current.preferences.find(pref => pref.type === SHIFT_COUNT) as
        | { countShiftTypes: string[] }
        | undefined;
      const affinity = result.current.preferences.find(pref => pref.type === SHIFT_AFFINITY) as
        | { shiftTypes: string[] }
        | undefined;
      const person = result.current.peopleData.items.find(item => item.id === 'P1');

      expect(request?.shiftType).toEqual(['DX']);
      expect(requirement?.shiftType).toEqual(['DX']);
      expect(successions?.pattern).toEqual(['DX', 'N']);
      expect(count?.countShiftTypes).toEqual(['DX', 'N']);
      expect(affinity?.shiftTypes).toEqual(['DX']);
      expect(person?.history).toEqual(['DX']);
      expect(result.current.preferences.some(pref => JSON.stringify(pref).includes('"D"'))).toBe(false);
    });
  });

  it('rejects renaming derived date IDs and leaves date-based preferences unchanged', async () => {
    const { result } = renderHook(() => useSchedulingData());
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined);

    act(() => {
      result.current.loadFromYaml({
        apiVersion: 'alpha',
        dates: {
          range: { startDate: '2026-05-01', endDate: '2026-05-02' },
          items: [{ id: '01', description: '' }, { id: '02', description: '' }],
          groups: [],
        },
        people: {
          items: [{ id: 'P1', description: '', history: [] }],
          groups: [],
          history: [],
        },
        shiftTypes: {
          items: [{ id: 'D', description: '' }],
          groups: [],
        },
        preferences: [
          { type: SHIFT_REQUEST, person: ['P1'], date: ['01'], shiftType: ['D'], weight: 1 },
          { type: SHIFT_TYPE_REQUIREMENT, date: ['01'], shiftType: ['D'], qualifiedPeople: ['P1'], requiredNumPeople: 1, weight: 2 },
          { type: SHIFT_TYPE_SUCCESSIONS, person: ['P1'], date: ['01'], pattern: ['D'], weight: 3 },
          { type: SHIFT_COUNT, person: ['P1'], countDates: ['01', '02'], countShiftTypes: ['D'], expression: 'x >= T', target: 1, weight: 4 },
          { type: SHIFT_AFFINITY, date: ['01'], people1: ['P1'], people2: ['P1'], shiftTypes: ['D'], weight: 5 },
        ],
        export: { formatting: [] },
      });
    });

    act(() => {
      result.current.updateItem(DataType.DATES, result.current.dateData, '01', '01X');
    });

    await waitFor(() => {
      const request = result.current.preferences.find(pref => pref.type === SHIFT_REQUEST) as { date: string[] } | undefined;
      const requirement = result.current.preferences.find(pref => pref.type === SHIFT_TYPE_REQUIREMENT) as { date: string[] } | undefined;
      const successions = result.current.preferences.find(pref => pref.type === SHIFT_TYPE_SUCCESSIONS) as { date: string[] } | undefined;
      const count = result.current.preferences.find(pref => pref.type === SHIFT_COUNT) as { countDates: string[] } | undefined;
      const affinity = result.current.preferences.find(pref => pref.type === SHIFT_AFFINITY) as { date: string[] } | undefined;

      expect(request?.date).toEqual(['01']);
      expect(requirement?.date).toEqual(['01']);
      expect(successions?.date).toEqual(['01']);
      expect(count?.countDates).toEqual(['01', '02']);
      expect(affinity?.date).toEqual(['01']);
      expect(result.current.dateData.items.some(item => item.id === '01X')).toBe(false);
    });

    expect(errorSpy).toHaveBeenCalledWith(
      expect.stringContaining('Cannot rename derived date item ID "01" to "01X"'),
    );
  });

  it('falls back cleanly when localStorage contains a partially corrupted nested state subtree', async () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      state: {
        apiVersion: 'alpha',
        description: 'broken',
        dates: { range: null, items: [], groups: [] },
        people: { items: [], groups: [], history: [] },
        shiftTypes: { items: [], groups: [] },
        preferences: [],
        export: { formatting: [] },
      },
      history: [],
      currentHistoryIndex: 0,
    }));
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined);

    const { result } = renderHook(() => useSchedulingData());

    await waitFor(() => {
      expect(result.current.peopleData.items.length).toBeGreaterThan(0);
    });

    expect(result.current.descriptionData).toBe('');
    expect(errorSpy).toHaveBeenCalled();
  });

  it('clamps malformed stored currentHistoryIndex values to the last valid entry', async () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      state: {
        apiVersion: 'alpha',
        description: 'current',
        dates: { range: { startDate: undefined, endDate: undefined }, items: undefined, groups: [] },
        people: { items: [{ id: 'P-current', description: '', history: [] }], groups: [], history: [] },
        shiftTypes: { items: [{ id: 'D', description: 'Day' }], groups: [] },
        preferences: [],
        export: { formatting: [] },
      },
      history: [
        {
          apiVersion: 'alpha',
          description: 'first',
          dates: { range: { startDate: undefined, endDate: undefined }, items: undefined, groups: [] },
          people: { items: [{ id: 'P-first', description: '', history: [] }], groups: [], history: [] },
          shiftTypes: { items: [{ id: 'D', description: 'Day' }], groups: [] },
          preferences: [],
          export: { formatting: [] },
        },
        {
          apiVersion: 'alpha',
          description: 'second',
          dates: { range: { startDate: undefined, endDate: undefined }, items: undefined, groups: [] },
          people: { items: [{ id: 'P-second', description: '', history: [] }], groups: [], history: [] },
          shiftTypes: { items: [{ id: 'D', description: 'Day' }], groups: [] },
          preferences: [],
          export: { formatting: [] },
        },
      ],
      currentHistoryIndex: 999,
    }));

    const { result } = renderHook(() => useSchedulingData());

    await waitFor(() => {
      expect(result.current.descriptionData).toBe('current');
    });

    act(() => {
      result.current.undo();
    });

    await waitFor(() => {
      expect(result.current.descriptionData).toBe('first');
    });

    act(() => {
      result.current.redo();
    });

    await waitFor(() => {
      expect(result.current.descriptionData).toBe('second');
    });
  });

  it('renames a shift-type group consistently across group-referenced preferences', async () => {
    const { result } = renderHook(() => useSchedulingData());

    act(() => {
      result.current.loadFromYaml({
        apiVersion: 'alpha',
        dates: {
          range: { startDate: '2026-06-01', endDate: '2026-06-01' },
          items: [{ id: '01', description: '' }],
          groups: [],
        },
        people: {
          items: [{ id: 'P1', description: '', history: [] }],
          groups: [],
          history: [],
        },
        shiftTypes: {
          items: [{ id: 'D', description: '' }, { id: 'N', description: '' }],
          groups: [{ id: 'DN', members: ['D', 'N'], description: '' }],
        },
        preferences: [
          { type: SHIFT_REQUEST, person: ['P1'], date: ['01'], shiftType: ['DN'], weight: 1 },
          { type: SHIFT_TYPE_REQUIREMENT, date: ['01'], shiftType: ['DN'], qualifiedPeople: ['P1'], requiredNumPeople: 1, weight: 2 },
          { type: SHIFT_COUNT, person: ['P1'], countDates: ['01'], countShiftTypes: ['DN'], expression: 'x >= T', target: 1, weight: 3 },
          { type: SHIFT_AFFINITY, date: ['01'], people1: ['P1'], people2: ['P1'], shiftTypes: ['DN'], weight: 4 },
        ],
        export: { formatting: [] },
      });
    });

    act(() => {
      result.current.updateGroup(DataType.SHIFT_TYPES, result.current.shiftTypeData, 'DN', 'DAYNIGHT');
    });

    await waitFor(() => {
      const request = result.current.preferences.find(pref => pref.type === SHIFT_REQUEST) as { shiftType: string[] } | undefined;
      const requirement = result.current.preferences.find(pref => pref.type === SHIFT_TYPE_REQUIREMENT) as { shiftType: string[] } | undefined;
      const count = result.current.preferences.find(pref => pref.type === SHIFT_COUNT) as { countShiftTypes: string[] } | undefined;
      const affinity = result.current.preferences.find(pref => pref.type === SHIFT_AFFINITY) as { shiftTypes: string[] } | undefined;

      expect(result.current.shiftTypeData.groups.some(group => group.id === 'DAYNIGHT')).toBe(true);
      expect(request?.shiftType).toEqual(['DAYNIGHT']);
      expect(requirement?.shiftType).toEqual(['DAYNIGHT']);
      expect(count?.countShiftTypes).toEqual(['DAYNIGHT']);
      expect(affinity?.shiftTypes).toEqual(['DAYNIGHT']);
    });
  });

  it('renames a people group referenced across mixed preference types', async () => {
    const { result } = renderHook(() => useSchedulingData());

    act(() => {
      result.current.loadFromYaml({
        apiVersion: 'alpha',
        dates: {
          range: { startDate: '2026-08-01', endDate: '2026-08-01' },
          items: [{ id: '01', description: '' }],
          groups: [],
        },
        people: {
          items: [{ id: 'P1', description: '', history: [] }, { id: 'P2', description: '', history: [] }],
          groups: [{ id: 'G1', members: ['P1', 'P2'], description: '' }],
          history: [],
        },
        shiftTypes: {
          items: [{ id: 'D', description: '' }],
          groups: [],
        },
        preferences: [
          { type: SHIFT_REQUEST, person: ['G1'], date: ['01'], shiftType: ['D'], weight: 1 },
          { type: SHIFT_COUNT, person: ['G1'], countDates: ['01'], countShiftTypes: ['D'], expression: 'x >= T', target: 1, weight: 2 },
          { type: SHIFT_AFFINITY, date: ['01'], people1: ['P1'], people2: ['G1'], shiftTypes: ['D'], weight: 3 },
          { type: SHIFT_TYPE_REQUIREMENT, date: ['01'], shiftType: ['D'], qualifiedPeople: ['P1', 'G1'], requiredNumPeople: 1, weight: 4 },
        ],
        export: { formatting: [] },
      });
    });

    act(() => {
      result.current.updateGroup(DataType.PEOPLE, result.current.peopleData, 'G1', 'G1X');
    });

    await waitFor(() => {
      const request = result.current.preferences.find(pref => pref.type === SHIFT_REQUEST) as { person: string[] } | undefined;
      const count = result.current.preferences.find(pref => pref.type === SHIFT_COUNT) as { person: string[] } | undefined;
      const affinity = result.current.preferences.find(pref => pref.type === SHIFT_AFFINITY) as { people2: string[] } | undefined;
      const requirement = result.current.preferences.find(pref => pref.type === SHIFT_TYPE_REQUIREMENT) as { qualifiedPeople: string[] } | undefined;

      expect(request?.person).toEqual(['G1X']);
      expect(count?.person).toEqual(['G1X']);
      expect(affinity?.people2).toEqual(['G1X']);
      expect(requirement?.qualifiedPeople).toEqual(['P1', 'G1X']);
    });
  });

  it('renames only the targeted reference when item and group IDs are mixed in preferences', async () => {
    const { result } = renderHook(() => useSchedulingData());

    act(() => {
      result.current.loadFromYaml({
        apiVersion: 'alpha',
        dates: {
          range: { startDate: '2026-08-02', endDate: '2026-08-02' },
          items: [{ id: '01', description: '' }],
          groups: [],
        },
        people: {
          items: [{ id: 'P1', description: '', history: [] }, { id: 'P2', description: '', history: [] }],
          groups: [{ id: 'G1', members: ['P1'], description: '' }],
          history: [],
        },
        shiftTypes: {
          items: [{ id: 'D', description: '' }],
          groups: [],
        },
        preferences: [
          { type: SHIFT_TYPE_REQUIREMENT, date: ['01'], shiftType: ['D'], qualifiedPeople: ['P1', 'G1'], requiredNumPeople: 1, weight: 1 },
          { type: SHIFT_AFFINITY, date: ['01'], people1: ['P1'], people2: ['G1'], shiftTypes: ['D'], weight: 2 },
        ],
        export: { formatting: [] },
      });
    });

    act(() => {
      result.current.updateItem(DataType.PEOPLE, result.current.peopleData, 'P1', 'P1X');
    });

    await waitFor(() => {
      const requirement = result.current.preferences.find(pref => pref.type === SHIFT_TYPE_REQUIREMENT) as { qualifiedPeople: string[] } | undefined;
      const affinity = result.current.preferences.find(pref => pref.type === SHIFT_AFFINITY) as { people1: string[]; people2: string[] } | undefined;

      expect(requirement?.qualifiedPeople).toEqual(['P1X', 'G1']);
      expect(affinity?.people1).toEqual(['P1X']);
      expect(affinity?.people2).toEqual(['G1']);
    });
  });

  it('removes old IDs after chained person renames', async () => {
    const { result } = renderHook(() => useSchedulingData());

    act(() => {
      result.current.loadFromYaml({
        apiVersion: 'alpha',
        dates: {
          range: { startDate: '2026-08-03', endDate: '2026-08-03' },
          items: [{ id: '01', description: '' }],
          groups: [],
        },
        people: {
          items: [{ id: 'P1', description: '', history: [] }],
          groups: [{ id: 'G1', members: ['P1'], description: '' }],
          history: [],
        },
        shiftTypes: {
          items: [{ id: 'D', description: '' }],
          groups: [],
        },
        preferences: [
          { type: SHIFT_REQUEST, person: ['P1'], date: ['01'], shiftType: ['D'], weight: 1 },
          { type: SHIFT_AFFINITY, date: ['01'], people1: ['P1'], people2: ['G1'], shiftTypes: ['D'], weight: 2 },
        ],
        export: { formatting: [] },
      });
    });

    act(() => {
      result.current.updateItem(DataType.PEOPLE, result.current.peopleData, 'P1', 'P1X');
    });

    await waitFor(() => {
      expect(result.current.peopleData.items.some(item => item.id === 'P1X')).toBe(true);
    });

    act(() => {
      result.current.updateItem(DataType.PEOPLE, result.current.peopleData, 'P1X', 'P1Y');
    });

    await waitFor(() => {
      const serialized = JSON.stringify(result.current.preferences);
      expect(result.current.peopleData.items.some(item => item.id === 'P1Y')).toBe(true);
      expect(serialized.includes('"P1"')).toBe(false);
      expect(serialized.includes('"P1X"')).toBe(false);
      expect(serialized.includes('"P1Y"')).toBe(true);
    });
  });

  it('keeps renamed references coherent when updatePreferencesByType runs afterward', async () => {
    const { result } = renderHook(() => useSchedulingData());

    act(() => {
      result.current.loadFromYaml({
        apiVersion: 'alpha',
        dates: {
          range: { startDate: '2026-08-04', endDate: '2026-08-04' },
          items: [{ id: '01', description: '' }],
          groups: [],
        },
        people: {
          items: [{ id: 'P1', description: '', history: [] }],
          groups: [{ id: 'G1', members: ['P1'], description: '' }],
          history: [],
        },
        shiftTypes: {
          items: [{ id: 'D', description: '' }],
          groups: [],
        },
        preferences: [
          { type: SHIFT_REQUEST, person: ['P1'], date: ['01'], shiftType: ['D'], weight: 1 },
        ],
        export: { formatting: [] },
      });
    });

    act(() => {
      result.current.updateItem(DataType.PEOPLE, result.current.peopleData, 'P1', 'P1X');
      result.current.updatePreferencesByType(SHIFT_REQUEST, [
        { type: SHIFT_REQUEST, person: ['P1X'], date: ['01'], shiftType: ['D'], weight: 3 },
        { type: SHIFT_REQUEST, person: ['G1'], date: ['01'], shiftType: ['D'], weight: 2 },
      ]);
    });

    await waitFor(() => {
      const requests = result.current.preferences.filter(pref => pref.type === SHIFT_REQUEST) as Array<{ person: string[]; weight: number }>;
      expect(requests.map(req => req.person[0])).toEqual(['P1X', 'G1']);
      expect(requests.map(req => req.weight)).toEqual([3, 2]);
    });
  });

});
