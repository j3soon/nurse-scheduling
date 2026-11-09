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

import { describe, expect, it } from 'vitest';
import { catalogs, detectLocale, isLocale, translator } from './messages';

const placeholders = (text: string) => [...text.matchAll(/\{(\w+)\}/g)].map(match => match[1]).sort();

describe('message catalogs', () => {
  it('falls back to English for unsupported browser languages', () => {
    expect(detectLocale(['fr-FR', 'en-US'])).toBe('en');
    expect(detectLocale([])).toBe('en');
    expect(isLocale('__proto__')).toBe(false);
    expect(isLocale('invalid')).toBe(false);
  });

  it('matches Traditional Chinese language and region tags in preference order', () => {
    for (const tag of ['zh-TW', 'zh-tw', 'zh-Hant', 'zh-Hant-TW', 'zh-HK', 'zh-MO', 'zh']) {
      expect(detectLocale([tag])).toBe('zh-TW');
    }
    expect(detectLocale(['fr-FR', 'zh-TW', 'en-US'])).toBe('zh-TW');
    expect(detectLocale(['en-GB', 'zh-TW'])).toBe('en');
    expect(detectLocale(['zh-Hans-CN', 'en'])).toBe('en');
    expect(translator('zh-TW')('Nurse Scheduling System')).toBe('護理人員排班系統');
  });

  it('preserves placeholders in every translation', () => {
    for (const catalog of Object.values(catalogs)) {
      expect(Object.keys(catalog).sort()).toEqual(Object.keys(catalogs.en).sort());
      for (const [key, message] of Object.entries(catalog)) {
        expect(message.trim(), key).not.toBe('');
        expect(placeholders(message), key).toEqual(placeholders(key));
      }
    }
  });

  it('substitutes values once and preserves user text literally', () => {
    const t = translator('en');
    expect(t('Remove "{value0}"', { value0: '$& <script>{value1}</script>' }))
      .toBe('Remove "$& <script>{value1}</script>"');
    expect(t('Unknown server error {details}')).toBe('Unknown server error {details}');
    expect(t('constructor')).toBe('constructor');
  });
});
