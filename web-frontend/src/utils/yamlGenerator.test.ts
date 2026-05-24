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

import { generateYamlFromState, isLeafArray, replacer } from '@/utils/yamlGenerator';

describe('yamlGenerator', () => {
  it('detects leaf arrays only', () => {
    expect(isLeafArray([1, 'a', true, null, undefined])).toBe(true);
    expect(isLeafArray([{ a: 1 }])).toBe(false);
    expect(isLeafArray('not-array')).toBe(false);
  });

  it('converts date values to YYYY-MM-DD through replacer', () => {
    const value = new Date(Date.UTC(2026, 1, 3, 12));
    expect(replacer('date', value)).toBe('2026-02-03');
  });

  it('emits flow style for leaf arrays in YAML output', () => {
    const yaml = generateYamlFromState({
      people: ['alice', 'bob'],
      meta: { enabled: true },
    });

    expect(yaml).toContain('people: [alice, bob]');
    expect(yaml).toContain('meta:\n  enabled: true');
    expect(yaml.endsWith('\n')).toBe(true);
  });
});
