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
  // The next model response starts a new assistant message in model context.
  endsRound?: true;
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
  const characters = Array.from(text);
  const chunks = Array.from({ length: Math.max(1, Math.ceil(characters.length / CHUNK_CHARS)) }, (_, index) => (
    characters.slice(index * CHUNK_CHARS, (index + 1) * CHUNK_CHARS).join('')
  ));
  return <div>
    <pre className="activity-output">{chunks[0]}</pre>
    {chunks.slice(1).map((chunk, index) => <details key={index} className="more-output">
      <summary role="button">Show more {label} ({formatCount(characters.length - (index + 1) * CHUNK_CHARS)} characters left)</summary>
      <pre className="activity-output">{chunk}</pre>
    </details>)}
  </div>;
}

function ToolBody({ entry }: { entry: ToolEntry }) {
  return (
    <div className="tool-body">
      {entry.arguments && entry.arguments !== '{}' && (
        <section aria-label="Tool arguments" className="tool-section">
          <h3 className="tool-heading">
            {entry.name === 'bash' ? 'Command' : 'Arguments'}{' '}
            <span className="tool-count">· {formatCount(characterCount(entry.arguments))} characters</span>
          </h3>
          <ChunkedText text={entry.arguments} label="arguments" />
        </section>
      )}
      {entry.result && (
        <section aria-label="Tool result" className="tool-section">
          <h3 className="tool-heading">
            Result{' '}
            <span className="tool-count">· {formatCount(characterCount(entry.result))} characters</span>
          </h3>
          <ChunkedText text={entry.result} label="output" />
        </section>
      )}
      {entry.state === 'interrupted' && !entry.result && (
        <p className="interrupted">The command did not return before the turn ended.</p>
      )}
      {entry.replayArguments !== undefined && (
        <section aria-label="Arguments sent in model context" className="replay-arguments">
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
    <pre className="schedule-diff">
      {removed.map((line, index) => (
        <span key={`removed-${index}`} className="removed">- {line}</span>
      ))}
      {added.map((line, index) => (
        <span key={`added-${index}`} className="added">+ {line}</span>
      ))}
    </pre>
  );
}

function activityColor(entry: ActivityEntry): string {
  if (entry.kind === 'schedule-applied' || (entry.kind === 'schedule-check' && entry.ok)) return 'activity-success';
  return entry.kind === 'schedule-check' ? 'activity-error' : 'activity-muted';
}

export function CompactionSummary({ entry }: { entry: CompactionActivity }) {
  return <>
    <p className="summary-explanation">{entry.invalidated ? 'Omitted from future model context because this run failed.'
      : 'The app supplies this summary to AI using the user role.'}</p>
    {!entry.invalidated && <p className="summary-explanation">{entry.keepMessages
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
        <div key={index} className={`activity-entry${entry.kind === 'schedule-check' ? ' model-input' : entry.kind === 'schedule-applied' || entry.kind === 'notice' ? ' app-notice' : ''}`}>
          {entry.kind === 'schedule-applied' && entry.notice && (
            <p role="status" className="schedule-notice">
              {entry.notice}
            </p>
          )}
          {index > 0 && (entry.kind === 'response' || entries[index - 1].kind === 'response') && (
            <hr className="activity-separator" />
          )}
          {(entry.kind === 'response' || entry.kind === 'reasoning') && entry.context === 'omitted' && (
            <p className="omitted-response">Incomplete response. Omitted from future model context.</p>
          )}
          {entry.kind === 'notice' ? (
            <p role="status" className="notice-message">{entry.text}</p>
          ) : entry.kind === 'response' ? (
            <>
              <AssistantMarkdown content={entry.text} />
              <p className="character-count">{formatCount(characterCount(entry.text))} characters</p>
            </>
          ) : (
            <details open={entry.kind === 'schedule-check' && !entry.ok ? true : undefined} className={`activity-details ${activityColor(entry)}`}>
              <summary className="activity-summary">{activitySummary(entry)}</summary>
              {entry.kind === 'schedule-check' && <p>Validation result sent to AI.</p>}
              {entry.kind === 'schedule-applied' && <p>Not sent to AI.</p>}
              <div className="activity-body">
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
