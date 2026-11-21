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

// Component for editing shift preferences for a specific person-date combination
'use client';

import { useI18n } from '@/i18n/I18nProvider';
import { useState, useEffect, useLayoutEffect, useRef } from 'react';
import { FiX, FiInfo } from 'react-icons/fi';
import { Item } from '@/types/scheduling';
import { getWeightDisplayLabel, getWeightColor, isValidWeightValue } from '@/utils/numberParsing';
import WeightInput from '@/components/WeightInput';
import { isImeCompositionKeyEvent } from '@/utils/keyboardEvents';

export interface ShiftPreferenceEdit {
  shiftTypeId: string;
  weight: number;
  description?: string;
}

type ShiftPreferenceDraft = Omit<ShiftPreferenceEdit, 'weight'> & { weight: number | string };

interface ShiftPreferenceEditorProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (preferences: ShiftPreferenceEdit[]) => void;
  personId: string;
  dateId: string;
  shiftTypes: Item[];
  initialPreferences: ShiftPreferenceEdit[];
  hasOtherRequests?: boolean;
}

export default function ShiftPreferenceEditor({
  isOpen,
  onClose,
  onSave,
  personId,
  dateId,
  shiftTypes,
  initialPreferences,
  hasOtherRequests,
}: ShiftPreferenceEditorProps) {
  const { t } = useI18n();
  const dialogRef = useRef<HTMLDivElement>(null);
  const [draftPreferences, setDraftPreferences] = useState<ShiftPreferenceDraft[] | null>(null);
  const preferences = draftPreferences ?? initialPreferences;

  useLayoutEffect(() => {
    if (!isOpen) return;

    const root = document.documentElement;
    const { overflow, scrollbarGutter } = root.style;
    const { scrollX, scrollY } = window;
    const previousFocus = document.activeElement;
    root.style.scrollbarGutter = 'stable';
    root.style.overflow = 'hidden';
    dialogRef.current?.focus({ preventScroll: true });

    return () => {
      root.style.overflow = overflow;
      root.style.scrollbarGutter = scrollbarGutter;
      if (previousFocus instanceof HTMLElement && previousFocus.isConnected) {
        previousFocus.focus({ preventScroll: true });
      }
      if (window.scrollX !== scrollX || window.scrollY !== scrollY) {
        window.scrollTo({ left: scrollX, top: scrollY, behavior: 'instant' });
      }
    };
  }, [isOpen]);

  const handleWeightChange = (shiftTypeId: string, index: number, weight: number | string) => {
    setDraftPreferences(prev => {
      const current = prev ?? initialPreferences;
      if (weight === 0) return current.filter((_, i) => i !== index);
      if (index === -1) return [...current, { shiftTypeId, weight }];
      return current.map((pref, i) => i === index ? { ...pref, weight } : pref);
    });
  };

  const handleDescriptionChange = (index: number, description: string) => {
    setDraftPreferences(prev => (prev ?? initialPreferences).map((pref, i) =>
      i === index ? { ...pref, description } : pref
    ));
  };

  const validateForm = (): boolean => {
    const newErrors: {[key: string]: string} = {};

    // Check for invalid weights
    for (const preference of preferences) {
      if (!isValidWeightValue(preference.weight)) {
        newErrors[preference.shiftTypeId] = t("Weight must be a valid number, Infinity, or -Infinity");
      }
    }

    return Object.keys(newErrors).length === 0;
  };

  function handleSave() {
    if (!validateForm()) return;
    // Convert all weights to numbers
    onSave(preferences.map(p => ({
      shiftTypeId: p.shiftTypeId,
      weight: p.weight as number,
      ...(p.description ? { description: p.description } : {}),
    })));
    setDraftPreferences(null);
    onClose();
  }

  function handleCancel() {
    setDraftPreferences(null);
    onClose();
  }

  // Handle global keydown for Enter/Escape when modal is open
  useEffect(() => {
    if (!isOpen) return;

    const handleGlobalKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Enter' && !(e.target instanceof HTMLTextAreaElement) && !isImeCompositionKeyEvent(e)) {
        e.preventDefault();
        handleSave();
      } else if (e.key === 'Escape') {
        e.preventDefault();
        handleCancel();
      }
    };

    document.addEventListener('keydown', handleGlobalKeyDown);
    return () => {
      document.removeEventListener('keydown', handleGlobalKeyDown);
    };
  });

  const clearAllPreferences = () => {
    setDraftPreferences([]);
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div ref={dialogRef} tabIndex={-1} role="dialog" aria-modal="true" aria-labelledby="shift-preference-matrix-title" className="bg-white rounded-xl shadow-2xl max-w-2xl w-full mx-4 max-h-[90vh] overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-gray-200 bg-gradient-to-r from-blue-50 to-indigo-50">
          <div>
            <h2 id="shift-preference-matrix-title" className="text-xl font-bold text-gray-800">
              {t("Shift Preference Matrix")}</h2>
            <p className="text-sm text-gray-600 mt-1">
              {t("Person: ")}<span className="font-medium text-blue-600">{personId}</span>{t(" • Date: ")}<span className="font-medium text-blue-600">{dateId}</span>
            </p>
          </div>
          <button
            onClick={handleCancel}
            className="text-gray-400 hover:text-gray-600 transition-colors p-2 hover:bg-white rounded-full"
          >
            <FiX className="h-6 w-6" />
          </button>
        </div>

        {/* Content */}
        <div className="overflow-y-auto overscroll-contain max-h-[calc(90vh-200px)]">
          <div className="p-6">
            {/* Info Box */}
            <div className="mb-6 p-4 bg-blue-50 border border-blue-200 rounded-lg">
              <div className="flex items-start gap-3">
                <FiInfo className="h-5 w-5 text-blue-600 mt-0.5 flex-shrink-0" />
                <div>
                  <h4 className="text-sm font-medium text-blue-800 mb-1">{t("Weight Scale Guide")}</h4>
                  <div className="text-xs text-blue-700 space-y-1">
                    <div><span className="font-medium text-green-600">{t("Positive (+1 to Infinity):")}</span>{t(" Prefer this shift type")}</div>
                    <div><span className="font-medium text-red-600">{t("Negative (-1 to -Infinity):")}</span>{t(" Avoid this shift type")}</div>
                    <div><span className="font-medium text-gray-600">{t("Zero (0):")}</span>{t(" No preference")}</div>
                  </div>
                </div>
              </div>
            </div>

            {hasOtherRequests && (
              <p className="mb-4 text-sm text-gray-700">
                {t("Edit descriptions for requests with multiple selectors in Current Shift Requests.")}
              </p>
            )}

            {/* Preferences Table */}
            <div className="bg-white border border-gray-200 rounded-lg overflow-hidden shadow-sm">
              <div className="bg-gray-50 px-6 py-3 border-b border-gray-200">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-gray-700">{t("Shift Type Preferences")}</h3>
                  <span className="text-xs text-gray-500">{shiftTypes.length}{t(" shift types")}</span>
                </div>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-600 uppercase tracking-wider w-auto">
                        {t("Shift Type")}</th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-600 uppercase tracking-wider">
                        {t("Description")}</th>
                      <th className="px-6 py-3 text-center text-xs font-medium text-gray-600 uppercase tracking-wider w-auto">
                        {t("Weight")}</th>
                      <th className="py-3 text-center text-xs font-medium text-gray-600 uppercase tracking-wider w-auto">
                        {t("Status")}</th>
                    </tr>
                  </thead>
                  <tbody className="bg-white divide-y divide-gray-200">
                    {shiftTypes.flatMap((shiftType, index) => {
                      const indices = preferences.flatMap((pref, i) => pref.shiftTypeId === shiftType.id ? [i] : []);
                      return (indices.length ? indices : [-1]).map((preferenceIndex, rowIndex) => {
                        const weight = preferences[preferenceIndex]?.weight ?? 0;
                        return (
                          <tr
                            key={`${shiftType.id}-${rowIndex}`}
                            className={`hover:bg-gray-50 transition-colors ${
                              index % 2 === 0 ? 'bg-white' : 'bg-gray-50/50'
                            }`}
                          >
                            {/* Shift Type */}
                            <td className="px-6 py-4 whitespace-nowrap">
                              <div className="font-medium text-sm text-gray-900">
                                {shiftType.id}
                              </div>
                            </td>

                            {/* Description */}
                            <td className="px-6 py-4">
                              <div className="text-sm text-gray-600">
                                {shiftType.description ? shiftType.description : <span className="italic text-gray-400">{t("No description")}</span>}
                              </div>
                            </td>

                            {/* Weight Input */}
                            <td className="px-6 py-4 text-center whitespace-nowrap">
                              <WeightInput
                                value={weight}
                                onChange={(value) => handleWeightChange(shiftType.id, preferenceIndex, value)}
                                compact={true}
                                label=""
                                placeholder=""
                              />
                            </td>

                            {/* Status Indicator */}
                            <td className="px-6 py-4 text-center whitespace-nowrap">
                              <div className={`inline-block px-2 py-1 rounded-full text-xs font-medium ${getWeightColor(weight)}`}>
                                {weight === 0 ? '—' : getWeightDisplayLabel(weight)}
                              </div>
                            </td>
                          </tr>
                        );
                      });
                    })}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Summary Section */}
            {preferences.length > 0 && (
              <div className="mt-6 p-4 bg-gradient-to-r from-blue-50 to-indigo-50 border border-blue-200 rounded-lg">
                <h4 className="text-sm font-semibold text-blue-800 mb-3 flex items-center gap-2">
                  <span>{t("Active Preferences Summary")}</span>
                  <span className="bg-blue-200 text-blue-800 px-2 py-1 rounded-full text-xs">
                    {preferences.length}
                  </span>
                </h4>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {preferences.map((pref, index) => ({ pref, index }))
                    .sort((a, b) => Number(b.pref.weight) - Number(a.pref.weight))
                    .map(({ pref, index }) => (
                      <div key={index} className="rounded-md bg-white px-3 py-2 shadow-sm">
                        <div className="flex items-center justify-between">
                          <span className="text-sm font-medium text-gray-700">{pref.shiftTypeId}</span>
                          <span className={`text-sm font-bold ${Number(pref.weight) > 0 ? 'text-green-600' : 'text-red-600'}`}>
                            {getWeightDisplayLabel(pref.weight)}
                          </span>
                        </div>
                        <label className="mt-2 block text-xs font-medium text-gray-700">
                          {t("Request description (optional)")}
                          <textarea
                            aria-label={t("Request description for {value0}", { value0: pref.shiftTypeId })}
                            value={pref.description ?? ''}
                            onChange={event => handleDescriptionChange(index, event.target.value)}
                            rows={2}
                            className="mt-1 block w-full rounded-md border border-gray-300 p-2 text-sm"
                          />
                        </label>
                      </div>
                    ))}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="flex flex-wrap justify-between items-center p-4 sm:p-6 border-t border-gray-200 bg-gray-50 gap-3">
          <button
            onClick={clearAllPreferences}
            className="px-4 py-2 text-gray-600 border border-gray-300 rounded-md hover:bg-gray-100 transition-colors font-medium"
          >
            {t("Clear All")}</button>
          <div className="flex gap-3">
            <button
              onClick={handleCancel}
              className="px-3 sm:px-6 py-2 text-gray-600 border border-gray-300 rounded-md hover:bg-gray-100 transition-colors font-medium"
            >
              {t("Cancel")}</button>
            <button
              onClick={handleSave}
              className="px-3 sm:px-6 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors font-medium"
            >
              {t("Save Preferences")}</button>
          </div>
        </div>
      </div>
    </div>
  );
}
