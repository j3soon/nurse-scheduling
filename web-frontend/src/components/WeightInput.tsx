/*
 * This file is part of Nurse Scheduling Project, see <https://github.com/j3soon/nurse-scheduling>.
 *
 * Copyright (C) 2023-2025 Johnson Sun
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

import React from 'react';
import { FiAlertCircle } from 'react-icons/fi';
import { parseWeightValue } from '@/utils/numberParsing';

interface WeightInputProps {
  value: number | string;
  onChange: (value: number | string) => void;
  error?: string;
  placeholder?: string;
  label?: string;
  compact?: boolean; // For smaller inputs like in popup
}

export default function WeightInput({
  value,
  onChange,
  error,
  placeholder = "e.g., -1, -10k, ∞",
  label = "Weight (priority)",
  compact = false
}: WeightInputProps) {
  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    onChange(parseWeightValue(e.target.value));
  };

  const handleSetInfinity = (isPositive: boolean) => {
    onChange(isPositive ? Infinity : -Infinity);
  };

  const baseInputClassName = compact
    ? "w-18 sm:w-20 px-2 sm:px-3 py-2 text-sm text-center"
    : "block w-full px-4 py-2 text-sm text-gray-900 bg-white";

  const inputClassName = `${baseInputClassName} border rounded-lg shadow-sm transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 hover:border-gray-400 ${
    error
      ? 'border-red-300 focus:border-red-500 focus:ring-red-200'
      : 'border-gray-300 focus:border-blue-500 focus:ring-blue-200'
  }`;

  const buttonClassName = compact
    ? "px-1 py-1 text-xs whitespace-nowrap"
    : "px-2 py-1 text-sm whitespace-nowrap";

  const containerClassName = compact
    ? "flex items-center gap-1"
    : "flex items-center gap-2";

  const buttonsContainerClassName = compact
    ? "flex flex-col gap-0.5"
    : "flex gap-2";

  return (
    <div>
      {!compact && label && (
        <label className="block text-sm font-medium text-gray-700 mb-2">
          {label}
        </label>
      )}
      <div className={containerClassName}>
        <input
          type="text"
          value={value}
          onChange={handleInputChange}
          className={inputClassName}
          placeholder={placeholder}
        />
        <div className={buttonsContainerClassName}>
          <button
            type="button"
            onClick={() => handleSetInfinity(true)}
            className={`${buttonClassName} bg-green-100 text-green-700 hover:bg-green-200 border border-green-300 rounded transition-colors focus:outline-none focus:ring-2 focus:ring-green-200`}
            title="Set to positive infinity (∞)"
          >
            +∞
          </button>
          <button
            type="button"
            onClick={() => handleSetInfinity(false)}
            className={`${buttonClassName} bg-red-100 text-red-700 hover:bg-red-200 border border-red-300 rounded transition-colors focus:outline-none focus:ring-2 focus:ring-red-200`}
            title="Set to negative infinity (-∞)"
          >
            -∞
          </button>
        </div>
      </div>
      {error && (
        <p className="mt-2 text-sm text-red-600 flex items-center gap-1">
          <FiAlertCircle className="h-4 w-4" />
          {error}
        </p>
      )}
    </div>
  );
}
