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

import { ERROR_SHOULD_NOT_HAPPEN } from '@/constants/errors';
import { getUniqueCopyLabel } from '@/utils/duplicateLabels';

export const duplicateEntryWithCopiedDescription = <T extends { description?: string }>(
  entries: T[],
  index: number,
  entryLabel: string
): T[] | null => {
  const sourceEntry = entries[index];
  if (!sourceEntry) {
    console.error(`Cannot duplicate ${entryLabel} at index ${index} - entry not found. ${ERROR_SHOULD_NOT_HAPPEN}`);
    return null;
  }

  const duplicatedEntry = {
    ...structuredClone(sourceEntry),
    description: getUniqueCopyLabel(
      sourceEntry.description,
      entries.map(entry => entry.description ?? '')
    ),
  };

  return [
    ...entries.slice(0, index + 1),
    duplicatedEntry,
    ...entries.slice(index + 1),
  ];
};
