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

import { createElement } from 'react';
import { act, render, renderHook, screen, waitFor } from '@testing-library/react';
import { SchedulingDataProvider, useSchedulingData } from '@/hooks/useSchedulingData';
import { loadStateFromStorage } from '@/hooks/schedulingStorage';
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

    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

    await waitFor(() => {
      expect(result.current.descriptionData).toBe('loaded from storage');
    });

    expect(result.current.dateData.range.startDate).toBeInstanceOf(Date);
    expect(result.current.dateData.range.endDate).toBeInstanceOf(Date);
    expect(result.current.peopleData.items.some(item => item.id === 'P1')).toBe(true);
    expect(result.current.dateData.items.map(item => item.id)).toEqual(['10', '11']);
  });

  it('keeps hydrated state in the provider when consumers remount', async () => {
    const getItemSpy = vi.spyOn(Storage.prototype, 'getItem');

    function Consumer() {
      useSchedulingData();
      return null;
    }

    const { rerender } = render(
      createElement(SchedulingDataProvider, null, createElement(Consumer))
    );

    await waitFor(() => {
      expect(getItemSpy).toHaveBeenCalledTimes(1);
    });

    rerender(createElement(SchedulingDataProvider));
    rerender(createElement(SchedulingDataProvider, null, createElement(Consumer)));

    expect(getItemSpy).toHaveBeenCalledTimes(1);
  });

  it('shows and dismisses the cross-tab change banner for matching storage events', async () => {
    render(createElement(SchedulingDataProvider));

    expect(screen.queryByText('Schedule data changed in another browser tab.')).not.toBeInTheDocument();

    act(() => {
      window.dispatchEvent(new StorageEvent('storage', {
        key: STORAGE_KEY,
        newValue: JSON.stringify({ changed: true }),
        storageArea: localStorage,
      }));
    });

    expect(screen.getByText('Schedule data changed in another browser tab.')).toBeInTheDocument();

    act(() => {
      screen.getByRole('button', { name: 'Dismiss' }).click();
    });

    expect(screen.queryByText('Schedule data changed in another browser tab.')).not.toBeInTheDocument();
  });

  it('shows the cross-tab change banner when localStorage is cleared in another tab', async () => {
    render(createElement(SchedulingDataProvider));

    act(() => {
      window.dispatchEvent(new StorageEvent('storage', {
        key: null,
        storageArea: localStorage,
      }));
    });

    expect(screen.getByText('Schedule data changed in another browser tab.')).toBeInTheDocument();
  });

  it('shows and dismisses YAML import warnings for preserved advanced reference syntax', async () => {
    function Importer() {
      const { loadFromYaml } = useSchedulingData();
      return createElement(
        'button',
        {
          type: 'button',
          onClick: () => loadFromYaml({
            apiVersion: 'alpha',
            people: {
              items: [{ id: 'P1', description: '', history: [] }, { id: 'P2', description: '', history: [] }],
              groups: [],
            },
            shiftTypes: {
              items: [{ id: 'D', description: '' }, { id: 'N', description: '' }],
              groups: [],
            },
            preferences: [
              {
                type: SHIFT_AFFINITY,
                date: ['ALL'],
                people1: [['P1', 'P2']],
                people2: ['P1'],
                shiftTypes: [['D', 'N']],
                weight: 1,
              },
            ],
          }),
        },
        'Import YAML'
      );
    }

    render(createElement(SchedulingDataProvider, null, createElement(Importer)));

    act(() => {
      screen.getByRole('button', { name: 'Import YAML' }).click();
    });

    expect(screen.getByText('Imported YAML contains advanced backend syntax.')).toBeInTheDocument();
    expect(screen.getByText(/preferences\[0\]\.people1/)).toBeInTheDocument();
    expect(screen.getByText(/preferences\[0\]\.shiftTypes/)).toBeInTheDocument();

    act(() => {
      screen.getByRole('button', { name: 'Dismiss' }).click();
    });

    expect(screen.queryByText('Imported YAML contains advanced backend syntax.')).not.toBeInTheDocument();
  });

  it('ignores storage events for unrelated keys and storage areas', async () => {
    render(createElement(SchedulingDataProvider));

    act(() => {
      window.dispatchEvent(new StorageEvent('storage', {
        key: 'unrelated-key',
        newValue: JSON.stringify({ changed: true }),
        storageArea: localStorage,
      }));
      window.dispatchEvent(new StorageEvent('storage', {
        key: STORAGE_KEY,
        newValue: JSON.stringify({ changed: true }),
        storageArea: sessionStorage,
      }));
    });

    expect(screen.queryByText('Schedule data changed in another browser tab.')).not.toBeInTheDocument();
  });

  it('reloads provider state from storage when the cross-tab banner reload action is clicked', async () => {
    const initialState = {
      state: {
        apiVersion: 'alpha',
        description: 'initial state',
        dates: {
          range: { startDate: undefined, endDate: undefined },
          items: undefined,
          groups: [],
        },
        people: {
          items: [{ id: 'P1', description: '', history: [] }],
          groups: [],
        },
        shiftTypes: {
          items: [{ id: 'D', description: 'Day' }],
          groups: [],
        },
        preferences: [{ type: 'at most one shift per day' }],
      },
      history: [
        {
          apiVersion: 'alpha',
          description: 'initial state',
          dates: {
            range: { startDate: undefined, endDate: undefined },
            items: undefined,
            groups: [],
          },
          people: {
            items: [{ id: 'P1', description: '', history: [] }],
            groups: [],
          },
          shiftTypes: {
            items: [{ id: 'D', description: 'Day' }],
            groups: [],
          },
          preferences: [{ type: 'at most one shift per day' }],
        },
      ],
      currentHistoryIndex: 0,
    };
    const updatedState = {
      ...initialState,
      state: {
        ...initialState.state,
        description: 'updated in another tab',
        people: {
          items: [{ id: 'P2', description: '', history: [] }],
          groups: [],
        },
      },
      history: [
        {
          ...initialState.history[0],
          description: 'updated in another tab',
          people: {
            items: [{ id: 'P2', description: '', history: [] }],
            groups: [],
          },
        },
      ],
    };

    localStorage.setItem(STORAGE_KEY, JSON.stringify(initialState));

    function Consumer() {
      const { descriptionData, peopleData } = useSchedulingData();
      return createElement(
        'div',
        null,
        createElement('span', null, descriptionData),
        createElement('span', null, peopleData.items[0]?.id)
      );
    }

    render(createElement(SchedulingDataProvider, null, createElement(Consumer)));

    await waitFor(() => {
      expect(screen.getByText('initial state')).toBeInTheDocument();
    });
    expect(screen.getByText('P1')).toBeInTheDocument();

    localStorage.setItem(STORAGE_KEY, JSON.stringify(updatedState));

    act(() => {
      window.dispatchEvent(new StorageEvent('storage', {
        key: STORAGE_KEY,
        oldValue: JSON.stringify(initialState),
        newValue: JSON.stringify(updatedState),
        storageArea: localStorage,
      }));
    });

    expect(screen.getByText('Schedule data changed in another browser tab.')).toBeInTheDocument();

    act(() => {
      screen.getByRole('button', { name: 'Reload data' }).click();
    });

    expect(screen.queryByText('Schedule data changed in another browser tab.')).not.toBeInTheDocument();
    expect(screen.getByText('updated in another tab')).toBeInTheDocument();
    expect(screen.getByText('P2')).toBeInTheDocument();
  });

  it('normalizes null qualified people from localStorage to all people', async () => {
    const storedState = {
      state: {
        apiVersion: 'alpha',
        description: 'loaded from storage',
        dates: {
          range: {
            startDate: '2026-01-10T12:00:00.000Z',
            endDate: '2026-01-10T12:00:00.000Z',
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
        preferences: [
          {
            type: SHIFT_TYPE_REQUIREMENT,
            shiftType: ['D'],
            requiredNumPeople: 1,
            qualifiedPeople: null,
            date: ['01'],
            weight: -1,
          },
        ],
      },
      history: [
        {
          apiVersion: 'alpha',
          description: 'loaded from storage',
          dates: {
            range: {
              startDate: '2026-01-10T12:00:00.000Z',
              endDate: '2026-01-10T12:00:00.000Z',
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
          preferences: [
            {
              type: SHIFT_TYPE_REQUIREMENT,
              shiftType: ['D'],
              requiredNumPeople: 1,
              qualifiedPeople: null,
              date: ['01'],
              weight: -1,
            },
          ],
        },
      ],
      currentHistoryIndex: 0,
    };

    localStorage.setItem(STORAGE_KEY, JSON.stringify(storedState));

    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

    await waitFor(() => {
      const requirement = result.current.getPreferencesByType(SHIFT_TYPE_REQUIREMENT)[0] as
        | { qualifiedPeople: string[] }
        | undefined;
      expect(requirement?.qualifiedPeople).toEqual([ALL]);
    });
  });

  it('falls back to the default state and logs when localStorage.getItem throws', async () => {
    const getItemSpy = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('storage unavailable');
    });
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined);

    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

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
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

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
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

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
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

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
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

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
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

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
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

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
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

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
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

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
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

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
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

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
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

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
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

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
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

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
    const { result, unmount } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

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

    const { result: reloadedResult } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });
    await waitFor(() => {
      const reloadedRequest = reloadedResult.current.preferences.find(pref => pref.type === SHIFT_REQUEST) as
        | { weight: number }
        | undefined;
      expect(reloadedRequest?.weight).toBe(Infinity);
    });
  });

  it('replaces stale people and shift-type metadata when loading sparse YAML sections', async () => {
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

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
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

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
        {
          type: SHIFT_REQUEST,
          person: ['Group 1'],
          date: ['03', '01'],
          shiftType: ['Day'],
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
      expect(requests).toHaveLength(4);
      expect(requests.map(req => [req.person[0], req.shiftType[0], req.weight])).toEqual([
        ['Person 1', 'D', 1],
        ['Person 1', 'D', 5],
        ['Person 2', 'N', 10],
        ['Group 1', 'Day', 1],
      ]);
      expect(requests[0].date).toEqual(['02', '03']);
      expect(requests[1].date).toEqual(['01', '02']);
      expect(requests[2].date).toEqual(['01', '03']);
      expect(requests[3].date).toEqual(['01', '03']);
    });
  });

  it('sorts SHIFT_TYPE_REQUIREMENT arrays in updatePreferencesByType', async () => {
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

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
      result.current.updatePreferencesByType(SHIFT_TYPE_REQUIREMENT, [
        {
          type: SHIFT_TYPE_REQUIREMENT,
          date: [ALL, '03', '01'],
          shiftType: ['Night', 'E', 'D'],
          qualifiedPeople: ['Group 1', 'Person 2', 'Person 1'],
          requiredNumPeople: 1,
          weight: -1,
        },
      ]);
    });

    await waitFor(() => {
      const requirement = result.current.preferences.find(pref => pref.type === SHIFT_TYPE_REQUIREMENT) as
        | { date: string[]; shiftType: string[]; qualifiedPeople: string[] }
        | undefined;
      expect(requirement?.shiftType).toEqual(['D', 'E', 'Night']);
      expect(requirement?.qualifiedPeople).toEqual(['Person 1', 'Person 2', 'Group 1']);
      expect(requirement?.date).toEqual(['01', '03', ALL]);
    });
  });

  it('sorts unordered arrays for remaining preference types in updatePreferencesByType', async () => {
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

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
      result.current.updatePreferencesByType(SHIFT_TYPE_SUCCESSIONS, [
        {
          type: SHIFT_TYPE_SUCCESSIONS,
          person: ['Group 1', 'Person 2', 'Person 1'],
          pattern: ['Night', 'D'],
          date: [ALL, '03', '01'],
          weight: -1,
        },
      ]);
    });

    await waitFor(() => {
      expect(result.current.preferences.some(pref => pref.type === SHIFT_TYPE_SUCCESSIONS)).toBe(true);
    });

    act(() => {
      result.current.updatePreferencesByType(SHIFT_COUNT, [
        {
          type: SHIFT_COUNT,
          person: ['Group 1', 'Person 2', 'Person 1'],
          countDates: [ALL, '03', '01'],
          countShiftTypes: ['Night', 'E', 'D'],
          expression: 'x >= T',
          target: 1,
          weight: -1,
        },
      ]);
    });

    await waitFor(() => {
      expect(result.current.preferences.some(pref => pref.type === SHIFT_COUNT)).toBe(true);
    });

    act(() => {
      result.current.updatePreferencesByType(SHIFT_AFFINITY, [
        {
          type: SHIFT_AFFINITY,
          date: [ALL, '03', '01'],
          people1: ['Group 1', 'Person 2', 'Person 1'],
          people2: ['Group 2', 'Person 3', 'Person 1'],
          shiftTypes: ['Night', 'E', 'D'],
          weight: 1,
        },
      ]);
    });

    await waitFor(() => {
      const successions = result.current.preferences.find(pref => pref.type === SHIFT_TYPE_SUCCESSIONS) as
        | { person: string[]; pattern: string[]; date: string[] }
        | undefined;
      const count = result.current.preferences.find(pref => pref.type === SHIFT_COUNT) as
        | { person: string[]; countDates: string[]; countShiftTypes: string[] }
        | undefined;
      const affinity = result.current.preferences.find(pref => pref.type === SHIFT_AFFINITY) as
        | { date: string[]; people1: string[]; people2: string[]; shiftTypes: string[] }
        | undefined;

      expect(successions?.person).toEqual(['Person 1', 'Person 2', 'Group 1']);
      expect(successions?.pattern).toEqual(['Night', 'D']);
      expect(successions?.date).toEqual(['01', '03', ALL]);
      expect(count?.person).toEqual(['Person 1', 'Person 2', 'Group 1']);
      expect(count?.countDates).toEqual(['01', '03', ALL]);
      expect(count?.countShiftTypes).toEqual(['D', 'E', 'Night']);
      expect(affinity?.date).toEqual(['01', '03', ALL]);
      expect(affinity?.people1).toEqual(['Person 1', 'Person 2', 'Group 1']);
      expect(affinity?.people2).toEqual(['Person 1', 'Person 3', 'Group 2']);
      expect(affinity?.shiftTypes).toEqual(['D', 'E', 'Night']);
    });
  });

  it('sorts unordered arrays in direct updatePreferences calls', async () => {
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

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
      result.current.updatePreferences([
        {
          type: SHIFT_COUNT,
          person: ['Group 1', 'Person 2', 'Person 1'],
          countDates: [ALL, '03', '01'],
          countShiftTypes: ['Night', 'E', 'D'],
          expression: 'x >= T',
          target: 1,
          weight: -1,
        },
      ]);
    });

    await waitFor(() => {
      const count = result.current.preferences.find(pref => pref.type === SHIFT_COUNT) as
        | { person: string[]; countDates: string[]; countShiftTypes: string[] }
        | undefined;
      expect(count?.person).toEqual(['Person 1', 'Person 2', 'Group 1']);
      expect(count?.countDates).toEqual(['01', '03', ALL]);
      expect(count?.countShiftTypes).toEqual(['D', 'E', 'Night']);
    });
  });

  it('blocks reserved keyword mutations for people items/groups', async () => {
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });
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
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

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
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

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
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

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
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });
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
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

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
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

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
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });
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
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

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

  it('sorts unordered export layout ID arrays without reordering rules', async () => {
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

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
      result.current.updateExportFormatting([
        {
          type: 'cell',
          people: ['Group 1', 'Person 2', 'Person 1'],
          dates: [ALL, '03', '01'],
          shiftTypes: ['Night', 'E', 'D'],
          backgroundColor: '#ffffff',
        },
        {
          type: 'row',
          people: ['Group 2', 'Person 3', 'Person 1'],
          backgroundColor: '#eeeeee',
        },
      ]);
      result.current.updateExportExtraColumns([
        {
          type: 'count',
          header: 'Count',
          countDates: [ALL, '03', '01'],
          countShiftTypes: ['Night', 'E', 'D'],
          countShiftTypeCoefficients: [['Night', 3], ['D', 2]],
        },
      ]);
      result.current.updateExportExtraRows([
        {
          type: 'count',
          header: 'People',
          countPeople: ['Group 1', 'Person 2', 'Person 1'],
          countShiftTypes: ['Night', 'E', 'D'],
        },
      ]);
    });

    await waitFor(() => {
      const formatting = result.current.exportData?.formatting;
      const cell = formatting?.[0] as
        | { people: string[]; dates: string[]; shiftTypes: string[] }
        | undefined;
      const row = formatting?.[1] as
        | { people: string[] }
        | undefined;
      expect(formatting?.map(rule => rule.type)).toEqual(['cell', 'row']);
      expect(cell?.people).toEqual(['Person 1', 'Person 2', 'Group 1']);
      expect(cell?.dates).toEqual(['01', '03', ALL]);
      expect(cell?.shiftTypes).toEqual(['D', 'E', 'Night']);
      expect(row?.people).toEqual(['Person 1', 'Person 3', 'Group 2']);
      expect(result.current.exportData?.extraColumns?.[0].countDates).toEqual(['01', '03', ALL]);
      expect(result.current.exportData?.extraColumns?.[0].countShiftTypes).toEqual(['D', 'E', 'Night']);
      expect(result.current.exportData?.extraColumns?.[0].countShiftTypeCoefficients).toEqual([['D', 2], ['Night', 3]]);
      expect(result.current.exportData?.extraRows?.[0].countPeople).toEqual(['Person 1', 'Person 2', 'Group 1']);
      expect(result.current.exportData?.extraRows?.[0].countShiftTypes).toEqual(['D', 'E', 'Night']);
    });
  });

  it('sorts unordered export layout ID arrays in updateExportConfig', async () => {
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

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
      result.current.updateExportConfig({
        formatting: [{
          type: 'cell',
          people: ['Group 1', 'Person 2', 'Person 1'],
          dates: [ALL, '03', '01'],
          shiftTypes: ['Night', 'E', 'D'],
          backgroundColor: '#ffffff',
        }],
        extraColumns: [{
          type: 'count',
          header: 'Count',
          countDates: [ALL, '03', '01'],
          countShiftTypes: ['Night', 'E', 'D'],
          countShiftTypeCoefficients: [['Night', 3], ['D', 2]],
        }],
        extraRows: [{
          type: 'count',
          header: 'People',
          countPeople: ['Group 1', 'Person 2', 'Person 1'],
          countShiftTypes: ['Night', 'E', 'D'],
        }],
      });
    });

    await waitFor(() => {
      const cell = result.current.exportData?.formatting?.[0] as
        | { people: string[]; dates: string[]; shiftTypes: string[] }
        | undefined;
      expect(cell?.people).toEqual(['Person 1', 'Person 2', 'Group 1']);
      expect(cell?.dates).toEqual(['01', '03', ALL]);
      expect(cell?.shiftTypes).toEqual(['D', 'E', 'Night']);
      expect(result.current.exportData?.extraColumns?.[0].countDates).toEqual(['01', '03', ALL]);
      expect(result.current.exportData?.extraColumns?.[0].countShiftTypes).toEqual(['D', 'E', 'Night']);
      expect(result.current.exportData?.extraColumns?.[0].countShiftTypeCoefficients).toEqual([['D', 2], ['Night', 3]]);
      expect(result.current.exportData?.extraRows?.[0].countPeople).toEqual(['Person 1', 'Person 2', 'Group 1']);
      expect(result.current.exportData?.extraRows?.[0].countShiftTypes).toEqual(['D', 'E', 'Night']);
    });
  });

  it('replaces existing export formatting when YAML omits the export section', async () => {
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

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

  it('replaces existing export extra rows and columns when loading sparse export YAML', async () => {
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

    act(() => {
      result.current.updateExportExtraColumns([
        { type: 'count', header: 'Old column', countDates: ['ALL'], countShiftTypes: ['D'] },
      ]);
      result.current.updateExportExtraRows([
        { type: 'count', header: 'Old row', countPeople: ['ALL'], countShiftTypes: ['D'] },
      ]);
    });

    await waitFor(() => {
      expect(result.current.exportData?.extraColumns).toHaveLength(1);
      expect(result.current.exportData?.extraRows).toHaveLength(1);
    });

    act(() => {
      result.current.loadFromYaml({
        apiVersion: 'alpha',
        description: 'sparse export replacement',
        dates: { range: { startDate: '2026-05-01', endDate: '2026-05-01' }, groups: [] },
        people: { items: [{ id: 'P1', description: '', history: [] }], groups: [], history: [] },
        shiftTypes: { items: [{ id: 'D', description: '' }], groups: [] },
        preferences: [{ type: 'at most one shift per day' }],
        export: { formatting: [] },
      });
    });

    await waitFor(() => {
      expect(result.current.descriptionData).toBe('sparse export replacement');
      expect(result.current.exportData).toEqual({ formatting: [] });
    });
  });

  it('cascades entity deletion through export layout rules and extra count rows', async () => {
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

    act(() => {
      result.current.loadFromYaml({
        apiVersion: 'alpha',
        dates: {
          range: { startDate: '2026-05-01', endDate: '2026-05-02' },
          items: [{ id: '01', description: '' }, { id: '02', description: '' }],
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
        preferences: [{ type: 'at most one shift per day' }],
        export: {
          formatting: [
            { type: 'row', people: ['P1', 'P2'], backgroundColor: '#111111' },
            { type: 'column', dates: ['01', '02'], backgroundColor: '#222222' },
            { type: 'cell', people: ['P1'], dates: ['02'], shiftTypes: ['N'], backgroundColor: '#333333' },
            { type: 'history header', backgroundColor: '#444444' },
          ],
          extraColumns: [
            {
              type: 'count',
              header: 'N on second day',
              countDates: ['02'],
              countShiftTypes: ['N'],
              countShiftTypeCoefficients: [['N', 2]],
            },
          ],
          extraRows: [
            { type: 'count', header: 'P1 nights', countPeople: ['P1'], countShiftTypes: ['N'] },
          ],
        },
      });
    });

    await waitFor(() => {
      expect(result.current.exportData?.formatting).toHaveLength(4);
    });

    act(() => {
      result.current.deleteItem(DataType.PEOPLE, result.current.peopleData, 'P1');
    });

    await waitFor(() => {
      expect(result.current.exportData?.formatting).toEqual([
        { type: 'row', people: ['P2'], backgroundColor: '#111111' },
        { type: 'column', dates: ['01', '02'], backgroundColor: '#222222' },
        { type: 'history header', backgroundColor: '#444444' },
      ]);
      expect(result.current.exportData?.extraRows).toEqual([]);
    });

    act(() => {
      result.current.deleteItem(DataType.SHIFT_TYPES, result.current.shiftTypeData, 'N');
    });

    await waitFor(() => {
      expect(result.current.exportData?.formatting).toEqual([
        { type: 'row', people: ['P2'], backgroundColor: '#111111' },
        { type: 'column', dates: ['01', '02'], backgroundColor: '#222222' },
        { type: 'history header', backgroundColor: '#444444' },
      ]);
      expect(result.current.exportData?.extraColumns).toEqual([]);
      expect(result.current.exportData?.extraRows).toEqual([]);
    });

    act(() => {
      result.current.updateDateRange({
        startDate: new Date('2026-05-01T12:00:00.000Z'),
        endDate: new Date('2026-05-01T12:00:00.000Z'),
      });
    });

    await waitFor(() => {
      expect(result.current.exportData?.formatting).toEqual([
        { type: 'row', people: ['P2'], backgroundColor: '#111111' },
        { type: 'column', dates: ['01'], backgroundColor: '#222222' },
        { type: 'history header', backgroundColor: '#444444' },
      ]);
    });
  });

  it('renames people, date groups, and shift types inside export layout state', async () => {
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

    act(() => {
      result.current.loadFromYaml({
        apiVersion: 'alpha',
        dates: {
          range: { startDate: '2026-05-01', endDate: '2026-05-01' },
          items: [{ id: '01', description: '' }],
          groups: [{ id: 'Weekend Team', members: ['01'], description: '' }],
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
        preferences: [{ type: 'at most one shift per day' }],
        export: {
          formatting: [
            { type: 'row', people: ['P1'], backgroundColor: '#111111' },
            { type: 'column', dates: ['Weekend Team'], backgroundColor: '#222222' },
            { type: 'cell', people: ['P1'], dates: ['Weekend Team'], shiftTypes: ['D'], backgroundColor: '#333333' },
          ],
          extraColumns: [
            {
              type: 'count',
              header: 'Day group count',
              countDates: ['Weekend Team'],
              countShiftTypes: ['D'],
              countShiftTypeCoefficients: [['D', 2]],
            },
          ],
          extraRows: [
            { type: 'count', header: 'Person day count', countPeople: ['P1'], countShiftTypes: ['D'] },
          ],
        },
      });
    });

    await waitFor(() => {
      expect(result.current.exportData?.formatting).toHaveLength(3);
    });

    act(() => {
      result.current.updateItem(DataType.PEOPLE, result.current.peopleData, 'P1', 'P1X');
      result.current.updateGroup(DataType.DATES, result.current.dateData, 'Weekend Team', 'Weekend Crew');
      result.current.updateItem(DataType.SHIFT_TYPES, result.current.shiftTypeData, 'D', 'DX');
    });

    await waitFor(() => {
      expect(result.current.exportData?.formatting).toEqual([
        { type: 'row', people: ['P1X'], backgroundColor: '#111111' },
        { type: 'column', dates: ['Weekend Crew'], backgroundColor: '#222222' },
        {
          type: 'cell',
          people: ['P1X'],
          dates: ['Weekend Crew'],
          shiftTypes: ['DX'],
          backgroundColor: '#333333',
        },
      ]);
      expect(result.current.exportData?.extraColumns).toEqual([
        {
          type: 'count',
          header: 'Day group count',
          countDates: ['Weekend Crew'],
          countShiftTypes: ['DX'],
          countShiftTypeCoefficients: [['DX', 2]],
        },
      ]);
      expect(result.current.exportData?.extraRows).toEqual([
        { type: 'count', header: 'Person day count', countPeople: ['P1X'], countShiftTypes: ['DX'] },
      ]);
    });
  });

  it('logs and skips sorting checks for invalid SHIFT_REQUEST person/shiftType shapes', async () => {
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });
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
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

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
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

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
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

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
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

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
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

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
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

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
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

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
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

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
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

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

  it('duplicates items and groups under the original with hook-generated copied IDs', async () => {
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

    act(() => {
      result.current.loadFromYaml({
        apiVersion: 'alpha',
        description: 'duplicate entities',
        dates: {
          range: { startDate: '2026-01-01', endDate: '2026-01-01' },
          items: [{ id: '01', description: 'Jan 1' }],
          groups: [],
        },
        people: {
          items: [
            { id: 'P1', description: 'Person 1', history: ['D'] },
            { id: 'P1 copy', description: 'Existing copy', history: [] },
          ],
          groups: [{ id: 'G1', description: 'Group 1', members: ['P1'] }],
          history: [],
        },
        shiftTypes: {
          items: [{ id: 'D', description: 'Day' }],
          groups: [],
        },
        preferences: [],
      });
    });

    await waitFor(() => {
      expect(result.current.peopleData.items.map(item => item.id)).toEqual(['P1', 'P1 copy']);
    });

    act(() => {
      result.current.duplicateItem(DataType.PEOPLE, result.current.peopleData, 'P1');
    });

    await waitFor(() => {
      expect(result.current.peopleData.items.map(item => item.id)).toEqual(['P1', 'P1 copy 2', 'P1 copy']);
      expect(result.current.peopleData.items[1]).toMatchObject({ id: 'P1 copy 2', description: 'Person 1', history: ['D'] });
      expect(result.current.peopleData.items[1].history).not.toBe(result.current.peopleData.items[0].history);
      expect(result.current.peopleData.groups[0].members).toEqual(['P1', 'P1 copy 2']);
    });

    act(() => {
      result.current.duplicateGroup(DataType.PEOPLE, result.current.peopleData, 'G1');
    });

    await waitFor(() => {
      expect(result.current.peopleData.groups.slice(0, 2).map(group => group.id)).toEqual(['G1', 'G1 copy']);
      expect(result.current.peopleData.groups[1].members).toEqual(['P1', 'P1 copy 2']);
      expect(result.current.peopleData.groups[1].members).not.toBe(result.current.peopleData.groups[0].members);
    });
  });

  it('duplicates preferences by type under the original with hook-generated copied descriptions', async () => {
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

    act(() => {
      result.current.loadFromYaml({
        apiVersion: 'alpha',
        description: 'duplicate preferences',
        dates: {
          range: { startDate: '2026-01-01', endDate: '2026-01-01' },
          items: [{ id: '01', description: 'Jan 1' }],
          groups: [],
        },
        people: {
          items: [{ id: 'P1', description: 'Person 1', history: [] }],
          groups: [],
          history: [],
        },
        shiftTypes: {
          items: [{ id: 'D', description: 'Day' }],
          groups: [],
        },
        preferences: [{
          type: SHIFT_COUNT,
          description: 'Original count',
          person: ['P1'],
          countDates: ['01'],
          countShiftTypes: ['D'],
          expression: 'x >= T',
          target: 1,
          weight: -1,
        }],
      });
    });

    act(() => {
      result.current.duplicatePreferenceByType(SHIFT_COUNT, 0);
    });

    await waitFor(() => {
      expect(result.current.getPreferencesByType(SHIFT_COUNT)).toMatchObject([
        { description: 'Original count', target: 1 },
        { description: 'Original count copy', target: 1 },
      ]);
    });
  });

  it('duplicates export entries under the original with hook-generated copied descriptions', async () => {
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

    act(() => {
      result.current.loadFromYaml({
        apiVersion: 'alpha',
        description: 'duplicate export entries',
        dates: {
          range: { startDate: '2026-01-01', endDate: '2026-01-01' },
          items: [{ id: '01', description: 'Jan 1' }],
          groups: [],
        },
        people: {
          items: [{ id: 'P1', description: 'Person 1', history: [] }],
          groups: [],
          history: [],
        },
        shiftTypes: {
          items: [{ id: 'D', description: 'Day' }],
          groups: [],
        },
        preferences: [],
        export: {
          formatting: [],
          extraColumns: [{
            type: 'count',
            header: 'Existing Score',
            countShiftTypes: ['D'],
            countDates: ['01'],
          }],
          extraRows: [],
        },
      });
    });

    act(() => {
      result.current.duplicateExportExtraColumn(0);
    });

    await waitFor(() => {
      expect(result.current.effectiveExportData.extraColumns).toMatchObject([
        { header: 'Existing Score' },
        { header: 'Existing Score', description: 'Copy' },
      ]);
    });
  });

  it('logs and no-ops when duplicate preference or export indexes are invalid', async () => {
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

    act(() => {
      result.current.loadFromYaml({
        apiVersion: 'alpha',
        description: 'invalid duplicate indexes',
        dates: {
          range: { startDate: '2026-01-01', endDate: '2026-01-01' },
          items: [{ id: '01', description: 'Jan 1' }],
          groups: [],
        },
        people: {
          items: [{ id: 'P1', description: 'Person 1', history: [] }],
          groups: [],
          history: [],
        },
        shiftTypes: {
          items: [{ id: 'D', description: 'Day' }],
          groups: [],
        },
        preferences: [{
          type: SHIFT_COUNT,
          description: 'Original count',
          person: ['P1'],
          countDates: ['01'],
          countShiftTypes: ['D'],
          expression: 'x >= T',
          target: 1,
          weight: -1,
        }],
        export: {
          formatting: [],
          extraColumns: [{
            type: 'count',
            header: 'Existing Score',
            countShiftTypes: ['D'],
            countDates: ['01'],
          }],
          extraRows: [],
        },
      });
    });

    act(() => {
      result.current.duplicatePreferenceByType(SHIFT_COUNT, 9);
      result.current.duplicateExportExtraColumn(9);
    });

    await waitFor(() => {
      expect(result.current.getPreferencesByType(SHIFT_COUNT)).toHaveLength(1);
      expect(result.current.effectiveExportData.extraColumns).toHaveLength(1);
      expect(errorSpy).toHaveBeenCalledWith(expect.stringContaining('Cannot duplicate shift count at index 9'));
      expect(errorSpy).toHaveBeenCalledWith(expect.stringContaining('Cannot duplicate export extra column at index 9'));
    });
  });

  it('renaming/deleting shift types cascades to preferences and people history', async () => {
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

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
          items: [{ id: 'P1', description: '', history: ['A', 'D', 'N'] }],
          groups: [],
          history: [],
        },
        shiftTypes: {
          items: [
            { id: 'A', description: 'Admin' },
            { id: 'D', description: 'Day' },
            { id: 'N', description: 'Night' },
          ],
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
            countShiftTypeCoefficients: [['D', 7]],
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
      const count = result.current.preferences.find(pref => pref.type === SHIFT_COUNT) as
        | { countShiftTypes: string[]; countShiftTypeCoefficients?: Array<[string, number]> }
        | undefined;
      expect(person?.history).toEqual(['A', 'DX', 'N']);
      expect(count?.countShiftTypes).toEqual(['DX']);
      expect(count?.countShiftTypeCoefficients).toEqual([['DX', 7]]);
      expect(result.current.preferences.some(pref => JSON.stringify(pref).includes('"D"'))).toBe(false);
      expect(result.current.preferences.some(pref => JSON.stringify(pref).includes('"DX"'))).toBe(true);
    });

    act(() => {
      result.current.deleteItem(DataType.SHIFT_TYPES, result.current.shiftTypeData, 'DX');
    });

    await waitFor(() => {
      const person = result.current.peopleData.items.find(item => item.id === 'P1');
      expect(person?.history).toEqual(['A', '', 'N']);
      expect(result.current.preferences.some(pref => pref.type === SHIFT_REQUEST)).toBe(false);
      expect(result.current.preferences.some(pref => pref.type === SHIFT_TYPE_REQUIREMENT)).toBe(false);
      expect(result.current.preferences.some(pref => pref.type === SHIFT_TYPE_SUCCESSIONS)).toBe(false);
      expect(result.current.preferences.some(pref => pref.type === SHIFT_COUNT)).toBe(false);
      expect(result.current.preferences.some(pref => pref.type === SHIFT_AFFINITY)).toBe(false);
    });
  });

  it('deleting dates cascades through date-based preferences', async () => {
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

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
      expect(result.current.preferences.some(pref => pref.type === SHIFT_TYPE_REQUIREMENT)).toBe(false);
      expect(result.current.preferences.some(pref => pref.type === SHIFT_COUNT)).toBe(false);
      expect(result.current.preferences.some(pref => pref.type === SHIFT_AFFINITY)).toBe(false);
      expect(result.current.preferences.some(pref => pref.type === SHIFT_TYPE_SUCCESSIONS)).toBe(false);
    });
  });

  it('renames date groups across all date-based preference fields', async () => {
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

    act(() => {
      result.current.loadFromYaml({
        apiVersion: 'alpha',
        description: 'date group succession rename',
        dates: {
          range: { startDate: '2026-12-01', endDate: '2026-12-02' },
          items: [
            { id: '01', description: 'Date 1' },
            { id: '02', description: 'Date 2' },
          ],
          groups: [{ id: 'Weekend Team', members: ['01', '02'], description: '' }],
        },
        people: {
          items: [{ id: 'P1', description: '', history: [] }],
          groups: [],
          history: [],
        },
        shiftTypes: {
          items: [
            { id: 'D', description: 'Day' },
            { id: 'N', description: 'Night' },
          ],
          groups: [],
        },
        preferences: [
          {
            type: SHIFT_TYPE_REQUIREMENT,
            shiftType: ['D'],
            requiredNumPeople: 1,
            qualifiedPeople: ['P1'],
            date: ['Weekend Team'],
            weight: 1,
          },
          { type: SHIFT_REQUEST, person: ['P1'], date: ['Weekend Team'], shiftType: ['D'], weight: 2 },
          {
            type: SHIFT_TYPE_SUCCESSIONS,
            person: ['P1'],
            pattern: ['D', 'N'],
            date: ['Weekend Team'],
            weight: -3,
          },
          {
            type: SHIFT_COUNT,
            person: ['P1'],
            countDates: ['Weekend Team'],
            countShiftTypes: ['D'],
            expression: 'x >= T',
            target: 1,
            weight: 4,
          },
          {
            type: SHIFT_AFFINITY,
            date: ['Weekend Team'],
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
      result.current.updateGroup(DataType.DATES, result.current.dateData, 'Weekend Team', 'Weekend Crew');
    });

    await waitFor(() => {
      const requirement = result.current.preferences.find(pref => pref.type === SHIFT_TYPE_REQUIREMENT) as
        | { date: string[] }
        | undefined;
      const request = result.current.preferences.find(pref => pref.type === SHIFT_REQUEST) as
        | { date: string[] }
        | undefined;
      const successions = result.current.preferences.find(pref => pref.type === SHIFT_TYPE_SUCCESSIONS) as
        | { date: string[] }
        | undefined;
      const count = result.current.preferences.find(pref => pref.type === SHIFT_COUNT) as
        | { countDates: string[] }
        | undefined;
      const affinity = result.current.preferences.find(pref => pref.type === SHIFT_AFFINITY) as
        | { date: string[] }
        | undefined;

      expect(requirement?.date).toEqual(['Weekend Crew']);
      expect(request?.date).toEqual(['Weekend Crew']);
      expect(successions?.date).toEqual(['Weekend Crew']);
      expect(count?.countDates).toEqual(['Weekend Crew']);
      expect(affinity?.date).toEqual(['Weekend Crew']);
      expect(JSON.stringify(result.current.preferences)).not.toContain('Weekend Team');
    });
  });

  it('deletes shift type successions when their date group reference is deleted', async () => {
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

    act(() => {
      result.current.loadFromYaml({
        apiVersion: 'alpha',
        description: 'date group succession delete',
        dates: {
          range: { startDate: '2026-12-01', endDate: '2026-12-02' },
          items: [
            { id: '01', description: 'Date 1' },
            { id: '02', description: 'Date 2' },
          ],
          groups: [{ id: 'Weekend Team', members: ['01', '02'], description: '' }],
        },
        people: {
          items: [{ id: 'P1', description: '', history: [] }],
          groups: [],
          history: [],
        },
        shiftTypes: {
          items: [
            { id: 'D', description: 'Day' },
            { id: 'N', description: 'Night' },
          ],
          groups: [],
        },
        preferences: [
          {
            type: SHIFT_TYPE_SUCCESSIONS,
            person: ['P1'],
            pattern: ['D', 'N'],
            date: ['Weekend Team'],
            weight: -1,
          },
        ],
        export: { formatting: [] },
      });
    });

    act(() => {
      result.current.deleteGroup(DataType.DATES, result.current.dateData, 'Weekend Team');
    });

    await waitFor(() => {
      expect(result.current.preferences.some(pref => pref.type === SHIFT_TYPE_SUCCESSIONS)).toBe(false);
    });
  });

  it('deletes shift type requirements when their only qualified person reference is deleted', async () => {
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

    act(() => {
      result.current.loadFromYaml({
        apiVersion: 'alpha',
        description: 'requirement qualified person delete',
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
        ],
        export: { formatting: [] },
      });
    });

    act(() => {
      result.current.deleteItem(DataType.PEOPLE, result.current.peopleData, 'P1');
    });

    await waitFor(() => {
      expect(result.current.preferences.some(pref => pref.type === SHIFT_TYPE_REQUIREMENT)).toBe(false);
    });
  });

  it('blocks reserved-keyword mutations for update item/group and remove-from-group across data types', async () => {
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });
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
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

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
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

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
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });
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
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });
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
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

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
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

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
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

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
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

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
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

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
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

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
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

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

    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

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

    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

    await waitFor(() => {
      expect(result.current.peopleData.items.length).toBeGreaterThan(0);
    });

    expect(result.current.descriptionData).toBe('');
    expect(errorSpy).toHaveBeenCalled();
  });

  it('converts numeric IDs in affinity and count preference shapes during YAML load', async () => {
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

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
            countShiftTypeCoefficients: [[10, 2], [11, 3]],
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
        | { person: string[]; countDates: string[]; countShiftTypes: string[]; countShiftTypeCoefficients?: Array<[string, number]> }
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
      expect(count?.countShiftTypeCoefficients).toEqual([['10', 2], ['11', 3]]);
    });
  });

  it('normalizes scalar YAML preference references into frontend arrays', async () => {
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

    act(() => {
      result.current.loadFromYaml({
        apiVersion: 'alpha',
        dates: {
          range: { startDate: '2026-04-01', endDate: '2026-04-01' },
          items: [{ id: 1, description: '' }],
          groups: [],
        },
        people: {
          items: [{ id: 'P1', description: '', history: [] }],
          groups: [],
        },
        shiftTypes: {
          items: [{ id: 'D', description: '' }],
          groups: [],
        },
        preferences: [
          {
            type: SHIFT_REQUEST,
            person: 'P1',
            date: 1,
            shiftType: 'D',
            weight: 1,
          },
          {
            type: SHIFT_TYPE_REQUIREMENT,
            shiftType: 'D',
            qualifiedPeople: 'P1',
            requiredNumPeople: 1,
            weight: 2,
          },
        ],
        export: { formatting: [] },
      });
    });

    await waitFor(() => {
      const request = result.current.preferences.find(pref => pref.type === SHIFT_REQUEST) as
        | { person: string[]; date: string[]; shiftType: string[] }
        | undefined;
      const requirement = result.current.preferences.find(pref => pref.type === SHIFT_TYPE_REQUIREMENT) as
        | { date: string[]; qualifiedPeople: string[]; shiftType: string[] }
        | undefined;

      expect(request).toMatchObject({
        person: ['P1'],
        date: ['01'],
        shiftType: ['D'],
      });
      expect(requirement).toMatchObject({
        date: [ALL],
        qualifiedPeople: ['P1'],
        shiftType: ['D'],
      });
      expect(result.current.yamlImportWarnings).toEqual([]);
    });
  });

  it('warns for backend-compatible shift request shapes outside the frontend editing subset', async () => {
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

    act(() => {
      result.current.loadFromYaml({
        apiVersion: 'alpha',
        dates: {
          range: { startDate: '2026-04-01', endDate: '2026-04-01' },
          items: [{ id: '01', description: '' }],
          groups: [],
        },
        people: {
          items: [{ id: 'P1', description: '', history: [] }, { id: 'P2', description: '', history: [] }],
          groups: [],
        },
        shiftTypes: {
          items: [{ id: 'D', description: '' }, { id: 'N', description: '' }],
          groups: [],
        },
        preferences: [
          {
            type: SHIFT_REQUEST,
            person: ['P1', 'P2'],
            date: ['01'],
            shiftType: ['D', 'N'],
            weight: 1,
          },
        ],
        export: { formatting: [] },
      });
    });

    await waitFor(() => {
      const request = result.current.preferences.find(pref => pref.type === SHIFT_REQUEST) as
        | { person: string[]; shiftType: string[] }
        | undefined;

      expect(request).toMatchObject({
        person: ['P1', 'P2'],
        shiftType: ['D', 'N'],
      });
      expect(result.current.yamlImportWarnings).toEqual([
        expect.stringContaining('preferences[0].person'),
        expect.stringContaining('preferences[0].shiftType'),
      ]);
    });
  });

  it('warns for backend-compatible shift count vector expressions outside the frontend editing subset', async () => {
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

    act(() => {
      result.current.loadFromYaml({
        apiVersion: 'alpha',
        dates: {
          range: { startDate: '2026-04-01', endDate: '2026-04-01' },
          items: [{ id: '01', description: '' }],
          groups: [],
        },
        people: {
          items: [{ id: 'P1', description: '', history: [] }],
          groups: [],
        },
        shiftTypes: {
          items: [{ id: 'D', description: '' }],
          groups: [],
        },
        preferences: [
          {
            type: SHIFT_COUNT,
            person: ['P1'],
            countDates: ['01'],
            countShiftTypes: ['D'],
            expression: ['x >= T', 'x <= T'],
            target: [1, 3],
            weight: 1,
          },
        ],
        export: { formatting: [] },
      });
    });

    await waitFor(() => {
      const count = result.current.preferences.find(pref => pref.type === SHIFT_COUNT) as
        | { expression: string[]; target: number[] }
        | undefined;

      expect(count).toMatchObject({
        expression: ['x >= T', 'x <= T'],
        target: [1, 3],
      });
      expect(result.current.yamlImportWarnings).toEqual([
        expect.stringContaining('preferences[0].expression'),
        expect.stringContaining('preferences[0].target'),
      ]);
    });
  });

  it('preserves nested YAML reference syntax and still updates nested references on rename', async () => {
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

    act(() => {
      result.current.loadFromYaml({
        apiVersion: 'alpha',
        people: {
          items: [{ id: 'P1', description: '', history: [] }, { id: 'P2', description: '', history: [] }],
          groups: [],
        },
        shiftTypes: {
          items: [{ id: 'D', description: '' }, { id: 'N', description: '' }],
          groups: [],
        },
        preferences: [
          {
            type: SHIFT_TYPE_REQUIREMENT,
            date: ['ALL'],
            shiftType: [['D', 'N']],
            qualifiedPeople: ['P1'],
            requiredNumPeople: 1,
            weight: 2,
          },
          {
            type: SHIFT_AFFINITY,
            date: ['ALL'],
            people1: [['P1', 'P2']],
            people2: ['P1'],
            shiftTypes: [['D', 'N']],
            weight: 1,
          },
        ],
        export: { formatting: [] },
      });
    });

    await waitFor(() => {
      expect(result.current.yamlImportWarnings).toEqual([
        expect.stringContaining('preferences[0].shiftType'),
        expect.stringContaining('preferences[1].people1'),
        expect.stringContaining('preferences[1].shiftTypes'),
      ]);
    });

    act(() => {
      result.current.updateItem(DataType.SHIFT_TYPES, result.current.shiftTypeData, 'D', 'Day');
      result.current.updateItem(DataType.PEOPLE, result.current.peopleData, 'P1', 'Alice');
    });

    await waitFor(() => {
      const requirement = result.current.preferences.find(pref => pref.type === SHIFT_TYPE_REQUIREMENT) as
        | { shiftType: string[][]; qualifiedPeople: string[] }
        | undefined;
      const affinity = result.current.preferences.find(pref => pref.type === SHIFT_AFFINITY) as
        | { people1: string[][]; people2: string[]; shiftTypes: string[][] }
        | undefined;

      expect(requirement?.shiftType).toEqual([['Day', 'N']]);
      expect(requirement?.qualifiedPeople).toEqual(['Alice']);
      expect(affinity?.people1).toEqual([['Alice', 'P2']]);
      expect(affinity?.people2).toEqual(['Alice']);
      expect(affinity?.shiftTypes).toEqual([['Day', 'N']]);
    });
  });

  it('cascades person deletion across multiple preference types in one state blob', async () => {
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

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
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

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
            countShiftTypeCoefficients: [['D', 2], ['N', 5]],
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
        | { countShiftTypes: string[]; countShiftTypeCoefficients?: Array<[string, number]> }
        | undefined;
      const affinity = result.current.preferences.find(pref => pref.type === SHIFT_AFFINITY) as
        | { shiftTypes: string[] }
        | undefined;
      const person = result.current.peopleData.items.find(item => item.id === 'P1');

      expect(request?.shiftType).toEqual(['DX']);
      expect(requirement?.shiftType).toEqual(['DX']);
      expect(successions?.pattern).toEqual(['DX', 'N']);
      expect(count?.countShiftTypes).toEqual(['DX', 'N']);
      expect(count?.countShiftTypeCoefficients).toEqual([['DX', 2], ['N', 5]]);
      expect(affinity?.shiftTypes).toEqual(['DX']);
      expect(person?.history).toEqual(['DX']);
      expect(result.current.preferences.some(pref => JSON.stringify(pref).includes('"D"'))).toBe(false);
    });
  });

  it('rejects renaming derived date IDs and leaves date-based preferences unchanged', async () => {
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });
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

    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

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

    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

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

  it('clamps stored currentHistoryIndex to zero when stored history is empty', () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      state: {
        apiVersion: 'alpha',
        description: 'empty history',
        dates: { range: { startDate: undefined, endDate: undefined }, items: undefined, groups: [] },
        people: { items: [{ id: 'P1', description: '', history: [] }], groups: [], history: [] },
        shiftTypes: { items: [{ id: 'D', description: 'Day' }], groups: [] },
        preferences: [],
        export: { formatting: [] },
      },
      history: [],
      currentHistoryIndex: 0,
    }));

    expect(loadStateFromStorage().currentHistoryIndex).toBe(0);
  });

  it('renames a shift-type group consistently across group-referenced preferences', async () => {
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

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
          { type: SHIFT_TYPE_SUCCESSIONS, person: ['P1'], date: ['01'], pattern: ['DN', 'D'], weight: -2 },
          {
            type: SHIFT_COUNT,
            person: ['P1'],
            countDates: ['01'],
            countShiftTypes: ['DN'],
            countShiftTypeCoefficients: [['DN', 4]],
            expression: 'x >= T',
            target: 1,
            weight: 3
          },
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
      const successions = result.current.preferences.find(pref => pref.type === SHIFT_TYPE_SUCCESSIONS) as { pattern: string[] } | undefined;
      const count = result.current.preferences.find(pref => pref.type === SHIFT_COUNT) as
        | { countShiftTypes: string[]; countShiftTypeCoefficients?: Array<[string, number]> }
        | undefined;
      const affinity = result.current.preferences.find(pref => pref.type === SHIFT_AFFINITY) as { shiftTypes: string[] } | undefined;

      expect(result.current.shiftTypeData.groups.some(group => group.id === 'DAYNIGHT')).toBe(true);
      expect(request?.shiftType).toEqual(['DAYNIGHT']);
      expect(requirement?.shiftType).toEqual(['DAYNIGHT']);
      expect(successions?.pattern).toEqual(['DAYNIGHT', 'D']);
      expect(count?.countShiftTypes).toEqual(['DAYNIGHT']);
      expect(count?.countShiftTypeCoefficients).toEqual([['DAYNIGHT', 4]]);
      expect(affinity?.shiftTypes).toEqual(['DAYNIGHT']);
    });
  });

  it('renames a people group referenced across mixed preference types', async () => {
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

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
          { type: SHIFT_TYPE_SUCCESSIONS, person: ['G1'], date: ['01'], pattern: ['D', 'N'], weight: -2 },
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
      const successions = result.current.preferences.find(pref => pref.type === SHIFT_TYPE_SUCCESSIONS) as { person: string[] } | undefined;
      const affinity = result.current.preferences.find(pref => pref.type === SHIFT_AFFINITY) as { people2: string[] } | undefined;
      const requirement = result.current.preferences.find(pref => pref.type === SHIFT_TYPE_REQUIREMENT) as { qualifiedPeople: string[] } | undefined;

      expect(request?.person).toEqual(['G1X']);
      expect(count?.person).toEqual(['G1X']);
      expect(successions?.person).toEqual(['G1X']);
      expect(affinity?.people2).toEqual(['G1X']);
      expect(requirement?.qualifiedPeople).toEqual(['P1', 'G1X']);
    });
  });

  it('renames only the targeted reference when item and group IDs are mixed in preferences', async () => {
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

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
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

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
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

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

  it('deleting a repeated shift type from history blanks only matching entries', async () => {
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

    act(() => {
      result.current.loadFromYaml({
        apiVersion: 'alpha',
        dates: { range: { startDate: '2026-09-01', endDate: '2026-09-01' }, items: [{ id: '01', description: '' }], groups: [] },
        people: {
          items: [{ id: 'P1', description: '', history: ['D', 'N', 'D', 'A'] }],
          groups: [],
          history: [],
        },
        shiftTypes: {
          items: [{ id: 'D', description: '' }, { id: 'N', description: '' }, { id: 'A', description: '' }],
          groups: [],
        },
        preferences: [{ type: 'at most one shift per day' }],
        export: { formatting: [] },
      });
    });

    act(() => {
      result.current.deleteItem(DataType.SHIFT_TYPES, result.current.shiftTypeData, 'D');
    });

    await waitFor(() => {
      expect(result.current.peopleData.items.find(item => item.id === 'P1')?.history).toEqual(['', 'N', '', 'A']);
    });
  });

  it('deleting an unrelated shift type leaves people history unchanged', async () => {
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

    act(() => {
      result.current.loadFromYaml({
        apiVersion: 'alpha',
        dates: { range: { startDate: '2026-09-01', endDate: '2026-09-01' }, items: [{ id: '01', description: '' }], groups: [] },
        people: {
          items: [{ id: 'P1', description: '', history: ['D', 'N'] }],
          groups: [],
          history: [],
        },
        shiftTypes: {
          items: [{ id: 'D', description: '' }, { id: 'N', description: '' }, { id: 'A', description: '' }],
          groups: [],
        },
        preferences: [{ type: 'at most one shift per day' }],
        export: { formatting: [] },
      });
    });

    act(() => {
      result.current.deleteItem(DataType.SHIFT_TYPES, result.current.shiftTypeData, 'A');
    });

    await waitFor(() => {
      expect(result.current.peopleData.items.find(item => item.id === 'P1')?.history).toEqual(['D', 'N']);
    });
  });

  it('deleting multiple shift types blanks history through repeated public deletions', async () => {
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

    act(() => {
      result.current.loadFromYaml({
        apiVersion: 'alpha',
        dates: { range: { startDate: '2026-09-01', endDate: '2026-09-01' }, items: [{ id: '01', description: '' }], groups: [] },
        people: {
          items: [{ id: 'P1', description: '', history: ['A', 'D', 'N', 'E'] }],
          groups: [],
          history: [],
        },
        shiftTypes: {
          items: [
            { id: 'A', description: '' },
            { id: 'D', description: '' },
            { id: 'N', description: '' },
            { id: 'E', description: '' },
          ],
          groups: [],
        },
        preferences: [{ type: 'at most one shift per day' }],
        export: { formatting: [] },
      });
    });

    act(() => {
      result.current.deleteItem(DataType.SHIFT_TYPES, result.current.shiftTypeData, 'D');
    });

    await waitFor(() => {
      expect(result.current.peopleData.items.find(item => item.id === 'P1')?.history).toEqual(['A', '', 'N', 'E']);
    });

    act(() => {
      result.current.deleteItem(DataType.SHIFT_TYPES, result.current.shiftTypeData, 'N');
    });

    await waitFor(() => {
      expect(result.current.peopleData.items.find(item => item.id === 'P1')?.history).toEqual(['A', '', '', 'E']);
    });
  });

  it('undoes and redoes shift-type deletion history blanking exactly', async () => {
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

    act(() => {
      result.current.loadFromYaml({
        apiVersion: 'alpha',
        dates: { range: { startDate: '2026-09-01', endDate: '2026-09-01' }, items: [{ id: '01', description: '' }], groups: [] },
        people: {
          items: [{ id: 'P1', description: '', history: ['A', 'D', 'N'] }],
          groups: [],
          history: [],
        },
        shiftTypes: {
          items: [{ id: 'A', description: '' }, { id: 'D', description: '' }, { id: 'N', description: '' }],
          groups: [],
        },
        preferences: [{ type: 'at most one shift per day' }],
        export: { formatting: [] },
      });
    });

    act(() => {
      result.current.deleteItem(DataType.SHIFT_TYPES, result.current.shiftTypeData, 'D');
    });

    await waitFor(() => {
      expect(result.current.peopleData.items.find(item => item.id === 'P1')?.history).toEqual(['A', '', 'N']);
    });

    act(() => {
      result.current.undo();
    });

    await waitFor(() => {
      expect(result.current.peopleData.items.find(item => item.id === 'P1')?.history).toEqual(['A', 'D', 'N']);
    });

    act(() => {
      result.current.redo();
    });

    await waitFor(() => {
      expect(result.current.peopleData.items.find(item => item.id === 'P1')?.history).toEqual(['A', '', 'N']);
    });
  });

  it('renames repeated shift-type history entries and export layout references', async () => {
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

    act(() => {
      result.current.loadFromYaml({
        apiVersion: 'alpha',
        dates: { range: { startDate: '2026-09-01', endDate: '2026-09-01' }, items: [{ id: '01', description: '' }], groups: [] },
        people: {
          items: [{ id: 'P1', description: '', history: ['D', 'N', 'D'] }],
          groups: [],
          history: [],
        },
        shiftTypes: {
          items: [{ id: 'D', description: '' }, { id: 'N', description: '' }],
          groups: [],
        },
        preferences: [{ type: 'at most one shift per day' }],
        export: {
          formatting: [{ type: 'cell', people: ['P1'], dates: ['01'], shiftTypes: ['D'], backgroundColor: '#111111' }],
          extraColumns: [{
            type: 'count',
            header: 'D count',
            countDates: ['01'],
            countShiftTypes: ['D'],
            countShiftTypeCoefficients: [['D', 2]],
          }],
          extraRows: [{ type: 'count', header: 'P1 D', countPeople: ['P1'], countShiftTypes: ['D'] }],
        },
      });
    });

    act(() => {
      result.current.updateItem(DataType.SHIFT_TYPES, result.current.shiftTypeData, 'D', 'DX');
    });

    await waitFor(() => {
      expect(result.current.peopleData.items.find(item => item.id === 'P1')?.history).toEqual(['DX', 'N', 'DX']);
      expect(result.current.exportData?.formatting?.[0]).toMatchObject({ shiftTypes: ['DX'] });
      expect(result.current.exportData?.extraColumns?.[0].countShiftTypes).toEqual(['DX']);
      expect(result.current.exportData?.extraColumns?.[0].countShiftTypeCoefficients).toEqual([['DX', 2]]);
      expect(result.current.exportData?.extraRows?.[0].countShiftTypes).toEqual(['DX']);
    });
  });

  it('removes person references across export formatting, extra rows, and extra columns together', async () => {
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

    act(() => {
      result.current.loadFromYaml({
        apiVersion: 'alpha',
        dates: { range: { startDate: '2026-09-01', endDate: '2026-09-01' }, items: [{ id: '01', description: '' }], groups: [] },
        people: {
          items: [{ id: 'P1', description: '', history: [] }, { id: 'P2', description: '', history: [] }],
          groups: [],
          history: [],
        },
        shiftTypes: { items: [{ id: 'D', description: '' }], groups: [] },
        preferences: [{ type: 'at most one shift per day' }],
        export: {
          formatting: [
            { type: 'row', people: ['P1', 'P2'], backgroundColor: '#111111' },
            { type: 'people header', people: ['P1'], backgroundColor: '#222222' },
          ],
          extraColumns: [{ type: 'count', header: 'D count', countDates: ['01'], countShiftTypes: ['D'] }],
          extraRows: [
            { type: 'count', header: 'Both people', countPeople: ['P1', 'P2'], countShiftTypes: ['D'] },
            { type: 'count', header: 'P1 only', countPeople: ['P1'], countShiftTypes: ['D'] },
          ],
        },
      });
    });

    act(() => {
      result.current.deleteItem(DataType.PEOPLE, result.current.peopleData, 'P1');
    });

    await waitFor(() => {
      expect(result.current.exportData?.formatting).toEqual([
        { type: 'row', people: ['P2'], backgroundColor: '#111111' },
      ]);
      expect(result.current.exportData?.extraColumns).toEqual([
        { type: 'count', header: 'D count', countDates: ['01'], countShiftTypes: ['D'] },
      ]);
      expect(result.current.exportData?.extraRows).toEqual([
        { type: 'count', header: 'Both people', countPeople: ['P2'], countShiftTypes: ['D'] },
      ]);
    });
  });

  it('removes stale export formatting rules when a date range shrinks', async () => {
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

    act(() => {
      result.current.loadFromYaml({
        apiVersion: 'alpha',
        dates: {
          range: { startDate: '2026-09-01', endDate: '2026-09-02' },
          items: [{ id: '01', description: '' }, { id: '02', description: '' }],
          groups: [],
        },
        people: { items: [{ id: 'P1', description: '', history: [] }], groups: [], history: [] },
        shiftTypes: { items: [{ id: 'D', description: '' }], groups: [] },
        preferences: [{ type: 'at most one shift per day' }],
        export: {
          formatting: [
            { type: 'column', dates: ['01', '02'], backgroundColor: '#111111' },
            { type: 'date header', dates: ['02'], backgroundColor: '#222222' },
          ],
          extraColumns: [
            { type: 'count', header: 'Both days', countDates: ['01', '02'], countShiftTypes: ['D'] },
            { type: 'count', header: 'Second day', countDates: ['02'], countShiftTypes: ['D'] },
          ],
        },
      });
    });

    act(() => {
      result.current.updateDateRange({
        startDate: new Date('2026-09-01T12:00:00.000Z'),
        endDate: new Date('2026-09-01T12:00:00.000Z'),
      });
    });

    await waitFor(() => {
      expect(result.current.exportData?.formatting).toEqual([
        { type: 'column', dates: ['01'], backgroundColor: '#111111' },
      ]);
      expect(result.current.exportData?.extraColumns).toEqual([
        { type: 'count', header: 'Both days', countDates: ['01'], countShiftTypes: ['D'] },
      ]);
    });
  });

  it('drops export date references during date identifier format transitions', async () => {
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

    act(() => {
      result.current.loadFromYaml({
        apiVersion: 'alpha',
        dates: {
          range: { startDate: '2026-05-01', endDate: '2026-05-02' },
          items: [{ id: '01', description: '' }, { id: '02', description: '' }],
          groups: [],
        },
        people: { items: [{ id: 'P1', description: '', history: [] }], groups: [], history: [] },
        shiftTypes: { items: [{ id: 'D', description: '' }], groups: [] },
        preferences: [{ type: 'at most one shift per day' }],
        export: {
          formatting: [{ type: 'column', dates: ['01', '02'], backgroundColor: '#111111' }],
          extraColumns: [{ type: 'count', header: 'Old dates', countDates: ['01', '02'], countShiftTypes: ['D'] }],
        },
      });
    });

    act(() => {
      result.current.updateDateRange({
        startDate: new Date('2026-05-31T12:00:00.000Z'),
        endDate: new Date('2026-06-01T12:00:00.000Z'),
      });
    });

    await waitFor(() => {
      expect(result.current.dateData.items.map(item => item.id)).toEqual(expect.arrayContaining(['05-31', '06-01']));
      expect(result.current.exportData?.formatting).toEqual([]);
      expect(result.current.exportData?.extraColumns).toEqual([]);
    });
  });

  it('replaces formatting and extra layout arrays when loading sparse export YAML', async () => {
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

    act(() => {
      result.current.loadFromYaml({
        apiVersion: 'alpha',
        description: 'full export',
        dates: { range: { startDate: '2026-09-01', endDate: '2026-09-01' }, items: [{ id: '01', description: '' }], groups: [] },
        people: { items: [{ id: 'P1', description: '', history: [] }], groups: [], history: [] },
        shiftTypes: { items: [{ id: 'D', description: '' }], groups: [] },
        preferences: [{ type: 'at most one shift per day' }],
        export: {
          formatting: [{ type: 'row', people: ['P1'], backgroundColor: '#111111' }],
          extraColumns: [{ type: 'count', header: 'Old column', countDates: ['01'], countShiftTypes: ['D'] }],
          extraRows: [{ type: 'count', header: 'Old row', countPeople: ['P1'], countShiftTypes: ['D'] }],
        },
      });
    });

    act(() => {
      result.current.loadFromYaml({
        apiVersion: 'alpha',
        description: 'sparse export',
        dates: { range: { startDate: '2026-09-01', endDate: '2026-09-01' }, groups: [] },
        people: { items: [{ id: 'P1', description: '', history: [] }], groups: [], history: [] },
        shiftTypes: { items: [{ id: 'D', description: '' }], groups: [] },
        preferences: [{ type: 'at most one shift per day' }],
        export: {
          formatting: [{ type: 'history header', backgroundColor: '#222222' }],
        },
      });
    });

    await waitFor(() => {
      expect(result.current.exportData).toEqual({
        formatting: [{ type: 'history header', backgroundColor: '#222222' }],
      });
    });
  });

  it('new schedule clears loaded export layout and people history back to defaults', async () => {
    const { result } = renderHook(() => useSchedulingData(), { wrapper: SchedulingDataProvider });

    act(() => {
      result.current.loadFromYaml({
        apiVersion: 'alpha',
        description: 'custom state',
        dates: { range: { startDate: '2026-09-01', endDate: '2026-09-01' }, items: [{ id: '01', description: '' }], groups: [] },
        people: { items: [{ id: 'P1', description: '', history: ['D'] }], groups: [], history: [] },
        shiftTypes: { items: [{ id: 'D', description: '' }], groups: [] },
        preferences: [{ type: 'at most one shift per day' }],
        export: {
          formatting: [{ type: 'row', people: ['P1'], backgroundColor: '#111111' }],
          extraColumns: [{ type: 'count', header: 'D count', countDates: ['01'], countShiftTypes: ['D'] }],
        },
      });
    });

    act(() => {
      result.current.createNewState();
    });

    await waitFor(() => {
      expect(result.current.descriptionData).toBe('');
      expect(result.current.peopleData.items[0].history).toEqual([]);
      expect(result.current.exportData).toBeUndefined();
    });
  });

});
