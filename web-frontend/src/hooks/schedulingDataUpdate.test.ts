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

import { DataType } from '@/types/scheduling';
import { SchedulingState } from './schedulingState';
import { applyDataUpdate } from './schedulingDataUpdate';

const baseState: SchedulingState = {
  apiVersion: 'test',
  description: 'schedule',
  dates: {
    range: {},
    items: [{ id: '01', description: 'Jan 1' }],
    groups: [{ id: 'Weekday', members: ['01'], description: '' }],
  },
  people: {
    items: [{ id: 'P1', description: '', history: [] }],
    groups: [],
  },
  shiftTypes: {
    items: [{ id: 'D', description: 'Day' }],
    groups: [],
  },
  preferences: [],
};

describe('applyDataUpdate', () => {
  it('updates date items and groups together', () => {
    const result = applyDataUpdate(baseState, DataType.DATES, {
      items: [{ id: '02', description: 'Jan 2' }],
      groups: [{ id: 'Weekend', members: ['02'], description: '' }],
    });

    expect(result.dates.items).toEqual([{ id: '02', description: 'Jan 2' }]);
    expect(result.dates.groups).toEqual([{ id: 'Weekend', members: ['02'], description: '' }]);
  });

  it('replaces people data', () => {
    const result = applyDataUpdate(baseState, DataType.PEOPLE, {
      items: [{ id: 'P2', description: '', history: ['N'] }],
      groups: [{ id: 'Team', members: ['P2'], description: '' }],
    });

    expect(result.people).toEqual({
      items: [{ id: 'P2', description: '', history: ['N'] }],
      groups: [{ id: 'Team', members: ['P2'], description: '' }],
    });
  });

  it('replaces shift type data', () => {
    const result = applyDataUpdate(baseState, DataType.SHIFT_TYPES, {
      items: [{ id: 'N', description: 'Night' }],
      groups: [{ id: 'Night', members: ['N'], description: '' }],
    });

    expect(result.shiftTypes).toEqual({
      items: [{ id: 'N', description: 'Night' }],
      groups: [{ id: 'Night', members: ['N'], description: '' }],
    });
  });
});
