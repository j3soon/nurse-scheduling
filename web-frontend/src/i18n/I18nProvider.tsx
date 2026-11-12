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
// This code is mostly AI generated.

'use client';

import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { detectLocale, isLocale, LOCALE_STORAGE_KEY, translator, type Locale } from './messages';

const defaultValue = { locale: 'en' as Locale, t: translator('en'), setLocale: (_locale: Locale) => {} };
const I18nContext = createContext(defaultValue);

export function I18nProvider({ children }: { children: ReactNode }) {
  // Static HTML and the first hydration render must use the same language.
  const [locale, updateLocale] = useState<Locale>('en');
  useEffect(() => {
    const readPreference = () => {
      let saved: string | null = null;
      try { saved = localStorage.getItem(LOCALE_STORAGE_KEY); } catch { /* Device storage can be disabled. */ }
      updateLocale(isLocale(saved) ? saved : detectLocale(navigator.languages?.length ? navigator.languages : [navigator.language]));
    };
    readPreference();
    const onStorage = (event: StorageEvent) => {
      if (event.key === LOCALE_STORAGE_KEY || event.key === null) readPreference();
    };
    window.addEventListener('storage', onStorage);
    window.addEventListener('languagechange', readPreference);
    return () => {
      window.removeEventListener('storage', onStorage);
      window.removeEventListener('languagechange', readPreference);
    };
  }, []);

  const value = useMemo(() => ({
    locale,
    t: translator(locale),
    setLocale: (selected: Locale) => {
      if (!isLocale(selected)) return;
      updateLocale(selected);
      try { localStorage.setItem(LOCALE_STORAGE_KEY, selected); } catch { /* Keep the in-memory choice. */ }
    },
  }), [locale]);

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  return <I18nContext.Provider value={value}>
    <title>{value.t('Nurse Scheduling System')}</title>
    <meta name="description" content={value.t('A user-friendly web app to automate the nurse scheduling task.')} />
    {children}
  </I18nContext.Provider>;
}

export function useI18n() {
  return useContext(I18nContext);
}
