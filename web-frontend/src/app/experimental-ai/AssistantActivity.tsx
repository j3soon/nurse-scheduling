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

import { useState } from 'react';

export interface ReasoningEntry {
  kind: 'reasoning';
  text: string;
}

export interface ToolEntry {
  kind: 'tool';
  name: string;
  arguments: string;
  result: string;
  ok: boolean;
}

export type ActivityEntry = ReasoningEntry | ToolEntry;

// Long output is revealed a chunk at a time, so an expanded row never floods the page.
const CHUNK_CHARS = 2000;

function formatCount(characters: number): string {
  return characters >= 1000 ? `${(characters / 1000).toFixed(1)}k` : `${characters}`;
}

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

function EditPreview({ entry }: { entry: ToolEntry }) {
  let removed = '';
  let added = '';
  try {
    const parsed = JSON.parse(entry.arguments) as { old_str?: unknown; new_str?: unknown };
    removed = typeof parsed.old_str === 'string' ? parsed.old_str : '';
    added = typeof parsed.new_str === 'string' ? parsed.new_str : '';
  } catch {
    // Fall back to the raw arguments when the model sent something unparsable.
  }
  if (!removed && !added) return <ChunkedText text={entry.arguments} label="arguments" />;

  return (
    <pre className="max-h-72 overflow-auto whitespace-pre-wrap break-words font-mono text-xs leading-relaxed">
      {removed.split('\n').map((line, index) => (
        <span key={`removed-${index}`} className="block text-red-700">- {line}</span>
      ))}
      {added.split('\n').map((line, index) => (
        <span key={`added-${index}`} className="block text-green-700">+ {line}</span>
      ))}
    </pre>
  );
}

function ToolBody({ entry }: { entry: ToolEntry }) {
  return (
    <div className="space-y-2">
      {entry.name === 'edit_schedule' ? (
        <EditPreview entry={entry} />
      ) : (
        entry.arguments && entry.arguments !== '{}' && <ChunkedText text={entry.arguments} label="arguments" />
      )}
      {entry.result && <ChunkedText text={entry.result} label="output" />}
    </div>
  );
}

function summaryOf(entry: ActivityEntry): string {
  if (entry.kind === 'reasoning') return `Reasoning · ${formatCount(entry.text.length)} characters`;
  return entry.ok ? entry.name : `${entry.name} · failed`;
}

export function AssistantActivity({ entries }: { entries: ActivityEntry[] }) {
  if (entries.length === 0) return null;

  return (
    <div aria-label="Assistant activity" className="mt-3 space-y-1 border-t border-gray-200 pt-2">
      {entries.map((entry, index) => (
        <details key={index} className="text-xs text-gray-500">
          <summary className="cursor-pointer select-none py-0.5 hover:text-gray-700">{summaryOf(entry)}</summary>
          <div className="mt-1 rounded bg-gray-50 p-2">
            {entry.kind === 'reasoning'
              ? <ChunkedText text={entry.text} label="reasoning" />
              : <ToolBody entry={entry} />}
          </div>
        </details>
      ))}
    </div>
  );
}
