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

import { activitySummary, characterCount, formatCharacterCount as formatCount, scheduleChangeLines } from './chatPresentation';

import { useState } from 'react';
import AssistantMarkdown from './AssistantMarkdown';

export interface ResponseEntry {
  kind: 'response';
  text: string;
  context?: 'complete' | 'omitted';
}

export interface ReasoningEntry {
  kind: 'reasoning';
  text: string;
  context?: 'complete' | 'omitted';
}

export interface ToolEntry {
  replayArguments?: string;
  kind: 'tool';
  toolCallId?: string;
  name: string;
  arguments: string;
  result: string;
  ok: boolean;
  state?: 'preparing' | 'running' | 'interrupted';
  argumentsCharacters?: number;
}

export interface ScheduleChangeEntry {
  kind: 'schedule-change';
  before: string;
  after: string;
}

// The trusted check the model received after a tool changed the working copy.
export interface ScheduleCheckEntry {
  kind: 'schedule-check';
  ok: boolean;
  text: string;
}

// The validated schedule the app applied when the response finished, with its differences.
export interface ScheduleAppliedEntry {
  kind: 'schedule-applied';
  text: string;
  runId?: string;
  notice?: string;
}

export interface CompactionActivity {
  kind: 'compaction';
  state: 'running' | 'completed' | 'failed' | 'interrupted' | 'skipped';
  reason: 'threshold' | 'overflow' | 'manual';
  text: string;
  summary?: string;
  keepMessages?: number;
  invalidated?: boolean;
  characters?: number;
  step?: number;
}

export type ActivityEntry =
  | { kind: 'notice'; text: string } | ResponseEntry | ReasoningEntry | ToolEntry | ScheduleChangeEntry | ScheduleCheckEntry | ScheduleAppliedEntry
  | CompactionActivity;

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
          Show more {label} ({formatCount(characterCount(text.slice(shown)))} characters left)
        </button>
      )}
    </div>
  );
}

function ToolBody({ entry }: { entry: ToolEntry }) {
  return (
    <div className="space-y-2">
      {entry.arguments && entry.arguments !== '{}' && (
        <section aria-label="Tool arguments" className="rounded border border-gray-200 bg-white p-2">
          <h3 className="mb-1 font-semibold text-gray-700">{entry.name === 'bash' ? 'Command' : 'Arguments'}</h3>
          <p className="mb-1 text-gray-500">{formatCount(characterCount(entry.arguments))} characters</p>
          <ChunkedText text={entry.arguments} label="arguments" />
        </section>
      )}
      {entry.result && (
        <section aria-label="Tool result" className="rounded border border-gray-200 bg-white p-2">
          <h3 className="mb-1 font-semibold text-gray-700">Result</h3>
          <p className="mb-1 text-gray-500">{formatCount(characterCount(entry.result))} characters</p>
          <ChunkedText text={entry.result} label="output" />
        </section>
      )}
      {entry.state === 'interrupted' && !entry.result && (
        <p className="text-xs text-red-700">The command did not return before the turn ended.</p>
      )}
      {entry.replayArguments !== undefined && (
        <section aria-label="Arguments sent in model context" className="rounded border border-amber-200 p-2">
          <p>Not executed. The original arguments above were truncated. Arguments sent in later model context:</p>
          <pre>{entry.replayArguments}</pre>
        </section>
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

function activityColor(entry: ActivityEntry): string {
  if (entry.kind === 'schedule-applied' || (entry.kind === 'schedule-check' && entry.ok)) return 'text-green-700';
  return entry.kind === 'schedule-check' ? 'text-red-700' : 'text-gray-500';
}

export function CompactionSummary({ entry }: { entry: CompactionActivity }) {
  return <>
    <p className="my-1">{entry.invalidated ? 'Omitted from future model context because this run failed.'
      : 'The app supplies this summary to AI using the user role.'}</p>
    {!entry.invalidated && <p className="my-1">{entry.keepMessages
      ? `The latest ${entry.keepMessages} messages remain unchanged after the summary.`
      : 'The summary replaces all earlier conversation messages in model context.'}</p>}
    <ChunkedText text={`[Conversation summary]\n${entry.summary}`} label="summary" />
  </>;
}

export function AssistantActivity({ entries }: { entries: ActivityEntry[] }) {
  if (entries.length === 0) return null;

  return (
    <div aria-label="Assistant activity">
      {entries.map((entry, index) => (
        <div key={index} className={entry.kind === 'schedule-check' ? 'ml-auto max-w-[95%]' : entry.kind === 'schedule-applied' || entry.kind === 'notice' ? 'mx-auto max-w-[95%]' : undefined}>
          {entry.kind === 'schedule-applied' && entry.notice && (
            <p role="status" className="my-2 rounded border border-amber-200 bg-amber-50 p-2 text-sm text-amber-900">
              {entry.notice}
            </p>
          )}
          {index > 0 && (entry.kind === 'response' || entries[index - 1].kind === 'response') && (
            <hr className="my-3 border-gray-200" />
          )}
          {(entry.kind === 'response' || entry.kind === 'reasoning') && entry.context === 'omitted' && (
            <p className="my-1 text-xs text-amber-800">Incomplete response. Omitted from future model context.</p>
          )}
          {entry.kind === 'notice' ? (
            <p role="status" className="my-2 text-sm text-amber-800">{entry.text}</p>
          ) : entry.kind === 'response' ? (
            <>
              <AssistantMarkdown content={entry.text} />
              <p className="mt-1 text-xs text-gray-500">{formatCount(characterCount(entry.text))} characters</p>
            </>
          ) : (
            <details open={entry.kind === 'schedule-check' && !entry.ok ? true : undefined} className={`text-xs ${activityColor(entry)}`}>
              <summary className="cursor-pointer select-none py-0.5 hover:text-gray-700">{activitySummary(entry)}</summary>
              {entry.kind === 'schedule-check' && <p>Validation result sent to AI.</p>}
              {entry.kind === 'schedule-applied' && <p>Not sent to AI.</p>}
              <div className="mt-1 rounded bg-gray-50 p-2">
                {entry.kind === 'tool'
                  ? <ToolBody entry={entry} />
                  : entry.kind === 'compaction'
                    ? <>
                      <p>{entry.text}</p>
                      {entry.summary !== undefined && <CompactionSummary entry={entry} />}
                    </>
                  : entry.kind === 'schedule-change'
                    ? <ScheduleChangePreview entry={entry} />
                    : <ChunkedText text={entry.text} label={entry.kind === 'reasoning' ? 'reasoning' : 'details'} />}
              </div>
            </details>
          )}
        </div>
      ))}
    </div>
  );
}
