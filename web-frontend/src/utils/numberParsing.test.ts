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

import {
  getWeightColor,
  getWeightDisplayLabel,
  isValidNumberValue,
  isValidWeightValue,
  isWeightNonPositive,
  parseNumberValue,
  parseWeightValue,
} from '@/utils/numberParsing';

describe('parseWeightValue', () => {
  it('parses infinity aliases', () => {
    expect(parseWeightValue('inf')).toBe(Infinity);
    expect(parseWeightValue('-∞')).toBe(-Infinity);
  });

  it('parses integer shorthand suffixes', () => {
    expect(parseWeightValue('2k')).toBe(2000);
    expect(parseWeightValue('3m')).toBe(3_000_000);
  });

  it('accepts shorthand with decimal numeric part when result is an integer', () => {
    expect(parseWeightValue('1.5k')).toBe(1500);
  });
});

describe('parseNumberValue', () => {
  it('parses shorthand suffixes with decimals', () => {
    expect(parseNumberValue('1.5k')).toBe(1500);
    expect(parseNumberValue('2.25m')).toBe(2_250_000);
  });

  it('returns original string for invalid numbers', () => {
    expect(parseNumberValue('abc')).toBe('abc');
  });
});

describe('weight helpers', () => {
  it('formats display labels for infinities and compact values', () => {
    expect(getWeightDisplayLabel(Infinity)).toBe('+∞');
    expect(getWeightDisplayLabel(-Infinity)).toBe('-∞');
    expect(getWeightDisplayLabel(1200)).toBe('+1.2k');
  });

  it('maps colors by sign and validity', () => {
    expect(getWeightColor(1)).toContain('text-green-600');
    expect(getWeightColor(-1)).toContain('text-red-600');
    expect(getWeightColor('invalid')).toContain('text-orange-800');
  });

  it('validates values correctly', () => {
    expect(isValidWeightValue(Infinity)).toBe(true);
    expect(isValidWeightValue('oops')).toBe(false);
    expect(isValidNumberValue(10)).toBe(true);
    expect(isValidNumberValue(Infinity)).toBe(false);
  });

  it('identifies only valid non-positive weights', () => {
    expect(isWeightNonPositive(-Infinity)).toBe(true);
    expect(isWeightNonPositive(-1)).toBe(true);
    expect(isWeightNonPositive(0)).toBe(true);
    expect(isWeightNonPositive(1)).toBe(false);
    expect(isWeightNonPositive(Infinity)).toBe(false);
    expect(isWeightNonPositive(NaN)).toBe(false);
    expect(isWeightNonPositive('invalid')).toBe(false);
  });
});
