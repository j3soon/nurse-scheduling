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

import type { ActivityEntry } from './AssistantActivity';
import type { ToolActivity, ToolStartActivity } from './aiClient';
import type { SessionEvent } from './sessionEvents';
import type { ChatMessageContent } from './chatTranscript';

// Plain-HTTP LAN origins lack randomUUID, so build the same version 4 UUID form from random bytes.
export function messageId(): string {
  if (typeof crypto.randomUUID === 'function') return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

// Streamed output of one assistant response. Foreground and replayed background
// streams both reduce these onto the message they own.
export type AssistantEvent =
  | { type: 'delta'; text: string }
  | { type: 'reasoning'; text: string }
  | Extract<SessionEvent, { type: 'compaction_start' | 'compaction_end' }>
  | { type: 'truncated' }
  | Extract<SessionEvent, { type: 'response_end' }>
  | { type: 'provider_retry'; message: string }
  | { type: 'done' | 'stopped' }
  | { type: 'error' | 'stale'; message: string }
  | { type: 'tool_start'; activity: ToolStartActivity }
  | { type: 'tool'; activity: ToolActivity }
  | { type: 'schedule_change'; before: string; after: string }
  | { type: 'schedule_applied'; diff: string; runId?: string; notice?: string };

export function startsVisibleOutput(event: AssistantEvent): boolean {
  return event.type === 'tool_start' || event.type === 'tool' || event.type === 'schedule_change'
    || ((event.type === 'delta' || event.type === 'reasoning') && event.text.length > 0);
}

function appendResponseActivity(entries: ActivityEntry[], text: string): ActivityEntry[] {
  const last = entries[entries.length - 1];
  if (last?.kind === 'response' && last.context === undefined) {
    return [...entries.slice(0, -1), { ...last, text: last.text + text }];
  }
  return [...entries, { kind: 'response', text }];
}

function appendReasoningActivity(entries: ActivityEntry[], text: string): ActivityEntry[] {
  const last = entries[entries.length - 1];
  // Consecutive reasoning belongs to one entry, so the order of work stays readable.
  if (last?.kind === 'reasoning' && last.context === undefined) {
    return [...entries.slice(0, -1), { ...last, text: last.text + text }];
  }
  return [...entries, { kind: 'reasoning', text }];
}

// Concurrent calls finish in any order, so a result completes the start that shares its ID.
function finishToolActivity(entries: ActivityEntry[], result: ToolActivity): ActivityEntry[] {
  const { scheduleCheck, ...tool } = result;
  const runningIndex = entries.findIndex(entry => (
    entry.kind === 'tool'
    && entry.state === 'running'
    && (tool.toolCallId === undefined ? entry.name === tool.name : entry.toolCallId === tool.toolCallId)
  ));
  // The check follows its tool, so the chat shows the same result the model received.
  const completed: ActivityEntry[] = [
    { kind: 'tool', ...tool },
    ...(scheduleCheck ? [{ kind: 'schedule-check' as const, ...scheduleCheck }] : []),
  ];
  if (runningIndex < 0) return [...entries, ...completed];
  return [...entries.slice(0, runningIndex), ...completed, ...entries.slice(runningIndex + 1)];
}

export function applyAssistantEvent<T extends ChatMessageContent>(message: T, event: AssistantEvent, occurredAt = Date.now()): T {
  const activity = message.activity ?? [];
  switch (event.type) {
    case 'response_end': {
      const context = event.stopReason === 'error' || event.stopReason === 'aborted' ? 'omitted' : 'complete';
      const ended = activity.map(entry => (
        event.contextNote && entry.kind === 'compaction' && entry.state === 'completed'
          ? { ...entry, invalidated: true }
          : (entry.kind === 'response' || entry.kind === 'reasoning') && entry.context === undefined
          ? { ...entry, context } : entry
      )) as ActivityEntry[];
      if (event.contextNote) {
        ended.push({ kind: 'notice', text: `Sent in future model context: ${event.contextNote}` });
      }
      return { ...message, activity: ended, ...(event.stopReason === 'length' ? { truncated: true } : {}) };
    }
    case 'provider_retry':
      return { ...message, activity: [...activity, { kind: 'notice', text: event.message }] };
    case 'delta':
      return {
        ...message,
        content: message.content + event.text,
        activity: appendResponseActivity(activity, event.text),
      };
    case 'reasoning':
      return { ...message, activity: appendReasoningActivity(activity, event.text) };
    case 'compaction_start':
      return { ...message, activity: [...activity, { kind: 'compaction', state: 'running', reason: event.reason,
        text: 'The conversation is being summarized.' }] };
    case 'compaction_end': {
      const state = event.success ? 'completed' : event.aborted ? 'interrupted' : 'failed';
      const entry: ActivityEntry = { kind: 'compaction', state, reason: event.reason,
        ...(event.summary === undefined ? {} : { summary: event.summary }),
        ...(event.keepMessages === undefined ? {} : { keepMessages: event.keepMessages }),
        text: event.success ? 'The conversation was summarized.' : event.aborted
          ? 'Summarization stopped. The original context was kept.' : 'Summarization failed. The original context was kept.' };
      const index = activity.findLastIndex(item => item.kind === 'compaction' && item.state === 'running');
      return { ...message, activity: index < 0 ? [...activity, entry] : [...activity.slice(0, index), entry, ...activity.slice(index + 1)] };
    }
    case 'truncated':
      return { ...message, truncated: true };
    case 'done':
      return completeResponse(message, occurredAt);
    case 'stopped':
      return stopResponse(message, occurredAt);
    case 'error':
      return failResponse(message, event.message, occurredAt);
    case 'stale':
      return staleResponse(message, event.message, occurredAt);
    case 'tool_start':
      return {
        ...message,
        activity: [...activity, { kind: 'tool', ...event.activity, result: '', ok: true, state: 'running' }],
      };
    case 'tool':
      return { ...message, activity: finishToolActivity(activity, event.activity) };
    case 'schedule_change':
      return {
        ...message,
        activity: [...activity, { kind: 'schedule-change', before: event.before, after: event.after }],
      };
    case 'schedule_applied': {
      const entry: ActivityEntry = { kind: 'schedule-applied', text: event.diff,
        ...(event.runId ? { runId: event.runId } : {}), ...(event.notice ? { notice: event.notice } : {}) };
      const retained = event.runId ? activity.filter(item => item.kind !== 'schedule-applied' || item.runId !== event.runId) : activity;
      return { ...message, activity: [...retained, entry] };
    }
  }
}

export function interruptRunningTools(entries: ActivityEntry[]): ActivityEntry[] {
  return entries.map(entry => (
    (entry.kind === 'tool' || entry.kind === 'compaction') && entry.state === 'running'
      ? { ...entry, state: 'interrupted' as const }
      : entry
  ));
}

export function resumeResponse<T extends ChatMessageContent>(message: T): T {
  return { ...message, status: 'pending', failureReason: undefined, responseCompletedAt: undefined };
}

export function completeResponse<T extends ChatMessageContent>(message: T, completedAt = Date.now()): T {
  return { ...message, status: undefined, failureReason: undefined, responseCompletedAt: completedAt };
}

export function failResponse<T extends ChatMessageContent>(message: T, fallbackText = '', completedAt = Date.now()): T {
  return {
    ...message,
    content: message.content || fallbackText,
    status: 'failed',
    failureReason: fallbackText || undefined,
    responseCompletedAt: completedAt,
    activity: interruptRunningTools(message.activity ?? []),
  };
}

export function staleResponse<T extends ChatMessageContent>(message: T, text: string, completedAt = Date.now()): T {
  return { ...failResponse(message, '', completedAt), content: text, activity: [{ kind: 'response', text }] };
}

// A stopped response keeps its partial output instead of gaining synthetic answer text.
export function stopResponse<T extends ChatMessageContent>(message: T, completedAt = Date.now()): T {
  return {
    ...message,
    status: 'stopped',
    responseCompletedAt: completedAt,
    activity: interruptRunningTools(message.activity ?? []),
  };
}

// A preview diffs against the previous working copy, or the browser schedule
// before the run's first preview. Other session events do not change an answer.
export function toAssistantEvent(
  event: SessionEvent,
  workingSchedule: { current: string | null },
  browserSchedule: { readonly current: string },
): AssistantEvent | null {
  switch (event.type) {
    case 'provider_retry': case 'delta': case 'reasoning': case 'truncated': case 'response_end': case 'tool_start': case 'tool':
    case 'compaction_start': case 'compaction_end':
      return event;
    case 'schedule_change': {
      const before = workingSchedule.current ?? browserSchedule.current;
      workingSchedule.current = event.scheduleYaml;
      return { type: 'schedule_change', before, after: event.scheduleYaml };
    }
    case 'schedule_applied':
      return { type: 'schedule_applied', runId: event.applied.runId, diff: event.applied.diff };
    default: return null;
  }
}
