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

import { FiArrowDown, FiArrowLeft, FiArrowRight, FiArrowUp } from 'react-icons/fi';

interface ReorderButtonsProps {
  label: string;
  onMove: (direction: -1 | 1) => void;
  canMoveUp: boolean;
  canMoveDown: boolean;
  horizontal?: boolean;
}

export function ReorderButtons({ label, onMove, canMoveUp, canMoveDown, horizontal = false }: ReorderButtonsProps) {
  const Back = horizontal ? FiArrowLeft : FiArrowUp;
  const Forward = horizontal ? FiArrowRight : FiArrowDown;
  // A lone movable entry has nowhere to go, so two disabled buttons would only add clutter.
  if (!canMoveUp && !canMoveDown) return null;
  return (
    <div className="hidden gap-1 [@media(pointer:coarse)]:inline-flex">
      {([-1, 1] as const).map(direction => {
        const Icon = direction === -1 ? Back : Forward;
        const action = horizontal ? (direction === -1 ? 'left' : 'right') : (direction === -1 ? 'up' : 'down');
        return (
          <button
            key={direction}
            type="button"
            aria-label={`Move ${label} ${action}`}
            disabled={direction === -1 ? !canMoveUp : !canMoveDown}
            onClick={event => { event.stopPropagation(); onMove(direction); }}
            className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded border border-gray-200 text-gray-600 hover:bg-gray-50 disabled:text-gray-300"
          >
            <Icon aria-hidden="true" className="h-4 w-4" />
          </button>
        );
      })}
    </div>
  );
}
