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
  const { locale, t } = useI18n();
  const [draft, setDraft] = useState('My ward');
  return <><span data-testid="language">{locale}</span><h1>{t('Nurse Scheduling System')}</h1>
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

  it('works when device storage is blocked and retains in-memory work', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('Blocked'); });
    render(<I18nProvider><Example /></I18nProvider>);
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Night ward' } });
    fireEvent(window, new Event('languagechange'));
    expect(screen.getByRole('textbox')).toHaveValue('Night ward');
    expect(screen.getByTestId('language')).toHaveTextContent('en');
  });
});
