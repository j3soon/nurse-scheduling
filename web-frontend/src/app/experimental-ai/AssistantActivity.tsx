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

import { activitySummary, formatCharacterCount as formatCount, scheduleChangeLines } from './chatPresentation';

import { useState } from 'react';
import AssistantMarkdown from './AssistantMarkdown';

export interface ResponseEntry {
  kind: 'response';
  text: string;
}

export interface ReasoningEntry {
  kind: 'reasoning';
  text: string;
}

export interface ToolEntry {
  kind: 'tool';
  toolCallId?: string;
  name: string;
  arguments: string;
  result: string;
  ok: boolean;
  state?: 'running' | 'interrupted';
}

export interface ScheduleChangeEntry {
  kind: 'schedule-change';
  before: string;
  after: string;
}

export type ActivityEntry = ResponseEntry | ReasoningEntry | ToolEntry | ScheduleChangeEntry;

// Long output is revealed a chunk at a time, so an expanded row never floods the page.
const CHUNK_CHARS = 2000;

function ChunkedText({ text, label }: { text: string; label: string }) {
  const [shown, setShown] = useState(CHUNK_CHARS);
  const remaining = text.length - shown;

  return (
    <div>
      <pre className="max-h-72 overflow-auto whitespace-pre-wrap break-words font-mono text-xs leading-relaxed text-gray-600">
        {text.slice(0, shown)}
      </pre>
      {remaining > 0 && (
        <button
          type="button"
          onClick={() => setShown(shown + CHUNK_CHARS)}
          className="mt-1 text-xs text-gray-500 underline underline-offset-2 hover:text-gray-700"
        >
          Show more {label} ({formatCount(remaining)} characters left)
        </button>
      )}
    </div>
  );
}

function ToolBody({ entry }: { entry: ToolEntry }) {
  return (
    <div className="space-y-2">
      {entry.arguments && entry.arguments !== '{}' && <ChunkedText text={entry.arguments} label="arguments" />}
      {entry.result && <ChunkedText text={entry.result} label="output" />}
      {entry.state === 'interrupted' && !entry.result && (
        <p className="text-xs text-red-700">The command did not return before the turn ended.</p>
      )}
    </div>
  );
}

function ScheduleChangePreview({ entry }: { entry: ScheduleChangeEntry }) {
  const { removed, added } = scheduleChangeLines(entry.before, entry.after);

  return (
    <pre className="max-h-72 overflow-auto whitespace-pre-wrap break-words font-mono text-xs leading-relaxed">
      {removed.map((line, index) => (
        <span key={`removed-${index}`} className="block text-red-700">- {line}</span>
      ))}
      {added.map((line, index) => (
        <span key={`added-${index}`} className="block text-green-700">+ {line}</span>
      ))}
    </pre>
  );
}

export function AssistantActivity({ entries }: { entries: ActivityEntry[] }) {
  if (entries.length === 0) return null;

  return (
    <div aria-label="Assistant activity">
      {entries.map((entry, index) => (
        <div key={index}>
          {index > 0 && (entry.kind === 'response' || entries[index - 1].kind === 'response') && (
            <hr className="my-3 border-gray-200" />
          )}
          {entry.kind === 'response' ? (
            <AssistantMarkdown content={entry.text} />
          ) : (
            <details className="text-xs text-gray-500">
              <summary className="cursor-pointer select-none py-0.5 hover:text-gray-700">{activitySummary(entry)}</summary>
              <div className="mt-1 rounded bg-gray-50 p-2">
                {entry.kind === 'reasoning'
                  ? <ChunkedText text={entry.text} label="reasoning" />
                  : entry.kind === 'tool'
                    ? <ToolBody entry={entry} />
                    : <ScheduleChangePreview entry={entry} />}
              </div>
            </details>
          )}
        </div>
      ))}
    </div>
  );
}
