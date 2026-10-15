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

import { type ReactNode, useId, useState } from 'react';
import { FiChevronDown } from 'react-icons/fi';

// Keep desktop content visible and let phone users expand secondary information.
// `openWhen` expands the phone panel once it becomes true, for content that needs attention.
export function MobileDetails({ label, children, desktopCollapsible = false, openWhen = false }: { label: string; children: ReactNode; desktopCollapsible?: boolean; openWhen?: boolean }) {
  const [expanded, setExpanded] = useState(false);
  const [openedForAttention, setOpenedForAttention] = useState(false);
  if (openWhen && !openedForAttention) {
    setOpenedForAttention(true);
    setExpanded(true);
  }
  const [desktopExpanded, setDesktopExpanded] = useState(true);
  const contentId = useId();
  return (
    <div className="min-w-0">
      <button
        type="button"
        aria-expanded={expanded}
        aria-controls={contentId}
        onClick={() => setExpanded(value => !value)}
        className="flex min-h-11 w-full items-center justify-between gap-2 rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-left text-sm font-medium text-gray-700 sm:hidden"
      >
        {label}
        <FiChevronDown aria-hidden="true" className={`shrink-0 ${expanded ? 'rotate-180' : ''}`} />
      </button>
      {desktopCollapsible && (
        <button
          type="button"
          aria-expanded={desktopExpanded}
          aria-controls={contentId}
          onClick={() => setDesktopExpanded(value => !value)}
          className="hidden w-full items-center justify-between gap-2 text-left font-semibold sm:flex"
        >
          {label}
          <FiChevronDown aria-hidden="true" className={`shrink-0 ${desktopExpanded ? 'rotate-180' : ''}`} />
        </button>
      )}
      <div id={contentId} className={`${expanded ? 'block' : 'hidden'} ${desktopExpanded ? 'sm:block' : 'sm:hidden'}`}>
        {children}
      </div>
    </div>
  );
}
