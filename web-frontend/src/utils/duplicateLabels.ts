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

const COPY_SUFFIX_PATTERN = /\s+copy(?: \d+)?$/i;

export function getUniqueCopyLabel(
  label: string | undefined,
  existingLabels: string[],
  fallbackLabel = 'Copy'
): string {
  const trimmedLabel = label?.trim() ?? '';
  const usedLabels = new Set(existingLabels);
  const firstCandidate = trimmedLabel
    ? `${trimmedLabel.replace(COPY_SUFFIX_PATTERN, '')} copy`
    : fallbackLabel;

  if (!usedLabels.has(firstCandidate)) {
    return firstCandidate;
  }

  let copyNumber = 2;
  while (usedLabels.has(`${firstCandidate} ${copyNumber}`)) {
    copyNumber += 1;
  }

  return `${firstCandidate} ${copyNumber}`;
}
