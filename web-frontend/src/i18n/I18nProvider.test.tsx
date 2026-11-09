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

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useState } from 'react';
import { I18nProvider, useI18n } from './I18nProvider';
import { LOCALE_STORAGE_KEY } from './messages';

function Example() {
  const { locale, t, setLocale } = useI18n();
  const [draft, setDraft] = useState('My ward');
  return <><span data-testid="language">{locale}</span><h1>{t('Nurse Scheduling System')}</h1>
    <button onClick={() => setLocale(locale === 'en' ? 'zh-TW' : 'en')}>Switch</button>
    <input aria-label="Draft" value={draft} onChange={event => setDraft(event.target.value)} /></>;
}

afterEach(() => { localStorage.clear(); vi.restoreAllMocks(); });

describe('language initialization', () => {
  it('uses English outside a provider and with invalid saved preferences', async () => {
    localStorage.setItem(LOCALE_STORAGE_KEY, 'unsupported');
    render(<I18nProvider><Example /></I18nProvider>);
    await waitFor(() => expect(document.documentElement.lang).toBe('en'));
    expect(screen.getByTestId('language')).toHaveTextContent('en');
    expect(screen.getByRole('heading')).toHaveTextContent('Nurse Scheduling System');
  });

  it('detects the browser, respects an explicit choice, and preserves draft state', async () => {
    vi.spyOn(navigator, 'languages', 'get').mockReturnValue(['zh-TW']);
    render(<I18nProvider><Example /></I18nProvider>);
    expect(await screen.findByRole('heading', { name: '護理人員排班系統' })).toBeVisible();
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Night ward' } });
    fireEvent.click(screen.getByRole('button', { name: 'Switch' }));
    expect(screen.getByRole('heading')).toHaveTextContent('Nurse Scheduling System');
    expect(localStorage.getItem(LOCALE_STORAGE_KEY)).toBe('en');
    fireEvent(window, new Event('languagechange'));
    expect(screen.getByTestId('language')).toHaveTextContent('en');
    expect(screen.getByRole('textbox')).toHaveValue('Night ward');
    fireEvent.click(screen.getByRole('button', { name: 'Switch' }));
    await waitFor(() => expect(document.documentElement.lang).toBe('zh-TW'));
    expect(document.title).toBe('護理人員排班系統');
  });

  it('follows another tab and falls back to detection when the saved choice is removed', () => {
    vi.spyOn(navigator, 'languages', 'get').mockReturnValue(['en-US']);
    localStorage.setItem(LOCALE_STORAGE_KEY, 'zh-TW');
    render(<I18nProvider><Example /></I18nProvider>);
    expect(screen.getByTestId('language')).toHaveTextContent('zh-TW');
    localStorage.removeItem(LOCALE_STORAGE_KEY);
    fireEvent(window, new StorageEvent('storage', { key: LOCALE_STORAGE_KEY, newValue: null }));
    expect(screen.getByTestId('language')).toHaveTextContent('en');
  });

  it('works when device storage is blocked and retains in-memory work', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('Blocked'); });
    render(<I18nProvider><Example /></I18nProvider>);
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Night ward' } });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('Blocked'); });
    fireEvent.click(screen.getByRole('button', { name: 'Switch' }));
    expect(screen.getByRole('heading')).toHaveTextContent('護理人員排班系統');
    fireEvent.click(screen.getByRole('button', { name: 'Switch' }));
    fireEvent(window, new Event('languagechange'));
    expect(screen.getByRole('textbox')).toHaveValue('Night ward');
    expect(screen.getByTestId('language')).toHaveTextContent('en');
  });
});
