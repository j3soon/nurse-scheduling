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

interface CollapsedTextProps {
  summary: string;
  text: string;
}

// Long raw text, such as the system prompt, collapsed until the reader opens it.
export default function CollapsedText({ summary, text }: CollapsedTextProps) {
  return (
    <details className="text-xs">
      <summary className="cursor-pointer select-none text-gray-500 hover:text-gray-700">{summary}</summary>
      <pre className="mt-1 max-h-72 overflow-auto whitespace-pre-wrap break-words font-mono leading-relaxed text-gray-700">
        {text}
      </pre>
    </details>
  );
}
