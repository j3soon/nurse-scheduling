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

import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import { I18nProvider } from '@/i18n/I18nProvider';
import { LOCALE_STORAGE_KEY, translator } from '@/i18n/messages';
import { CostDetails } from './CostDetails';
import { costLabel, formatSpeed, turnDetailsLabel, turnMeasurementLines } from './costs';

const summary = { usd: '0.01', calls: 2, pending: 1, unavailable: 1 };
afterEach(() => localStorage.removeItem(LOCALE_STORAGE_KEY));

it('retains English presentation defaults for exports and other callers', () => {
  expect(costLabel(summary)).toBe('$0.0100 · 2 calls · 1 pending · 1 cost unavailable');
  expect(turnDetailsLabel(summary)).toBe('Turn details · ~$0.0100 · Speed unavailable · 2 calls · 1 pending · 1 cost unavailable');
  expect(turnMeasurementLines(summary)).toContain('Estimated cost: $0.0100');
  expect(turnMeasurementLines(summary)).toContain('Speed measured for 0 of 2 calls.');
});

it('translates cost states and measurement explanations with the supplied translator', () => {
  const t = translator('zh-TW');
  expect(costLabel(summary, true, t)).toBe('$0.0100 · 2 次呼叫 · 1 次待計算 · 1 次費用無法取得');
  expect(formatSpeed(undefined, undefined, t)).toBe('無法取得速度');
  expect(turnMeasurementLines(summary, t)).toContain('已測量 2 次呼叫中的 0 次串流速度。');
});

it('passes the selected language into visible turn details', async () => {
  localStorage.setItem(LOCALE_STORAGE_KEY, 'zh-TW');
  render(<I18nProvider><CostDetails summary={summary} calls={[]} running /></I18nProvider>);
  const heading = await screen.findByText('此輪詳細資料 · ~$0.0100 · 無法取得速度 · 2 次呼叫 · 1 次待計算 · 1 次費用無法取得');
  fireEvent.click(heading);
  expect(screen.getByText('預估費用：$0.0100')).toBeVisible();
  expect(screen.getByText('供應商串流速度：無法取得速度')).toBeVisible();
});
