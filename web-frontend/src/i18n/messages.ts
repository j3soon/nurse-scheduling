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

import { en } from './en';

export type Locale = 'en';
export type MessageKey = keyof typeof en;
export type Catalog = Record<MessageKey, string>;
export type MessageValues = Record<string, string | number | undefined>;
export type Translator = (message: string, values?: MessageValues) => string;
export const catalogs: Record<Locale, Catalog> = { en };
export const LOCALE_STORAGE_KEY = 'nurse-scheduling-language';
export const localeNames: Record<Locale, string> = { en: 'English' };

export function isLocale(value: unknown): value is Locale {
  return typeof value === 'string' && Object.hasOwn(catalogs, value);
}

export function detectLocale(languages: readonly string[]): Locale {
  for (const language of languages) {
    if (isLocale(language)) return language;
    const base = language.split('-')[0].toLowerCase();
    if (isLocale(base)) return base;
  }
  return 'en';
}

export function translator(locale: Locale): Translator {
  return (message, values) => {
    const catalog = catalogs[locale];
    const template = Object.hasOwn(catalog, message) ? catalog[message as MessageKey] : message;
    // Replace once so braces and dollar signs in user values stay literal.
    return template.replace(/\{(\w+)\}/g, (match, key: string) => (
      values && Object.hasOwn(values, key) ? String(values[key]) : match
    ));
  };
}
