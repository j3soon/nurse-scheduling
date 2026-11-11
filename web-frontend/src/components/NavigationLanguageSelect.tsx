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

import { FiGlobe } from 'react-icons/fi';
import { useI18n } from '@/i18n/I18nProvider';
import { isLocale, localeNames } from '@/i18n/messages';

export default function NavigationLanguageSelect() {
  const { locale, setLocale, t } = useI18n();
  return (
    <div className="relative flex h-11 w-11 shrink-0 items-center justify-center rounded text-gray-500 hover:bg-gray-100 hover:text-gray-700 focus-within:ring-2 focus-within:ring-blue-500 focus-within:ring-offset-1">
      <FiGlobe aria-hidden="true" className="h-4 w-4" />
      <select
        aria-label={t('Change language')}
        title={`${t('Language')}: ${localeNames[locale]}`}
        onKeyDownCapture={event => {
          // Page form shortcuts must not submit or cancel a draft from this picker.
          event.stopPropagation();
        }}
        value={locale}
        onChange={event => {
          if (isLocale(event.target.value)) setLocale(event.target.value);
        }}
        className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
      >
        {Object.entries(localeNames).map(([value, name]) => (
          <option key={value} value={value} lang={value}>{name}</option>
        ))}
      </select>
    </div>
  );
}
