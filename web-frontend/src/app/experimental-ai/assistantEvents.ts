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
import type { ChatExportMessage } from './chatExport';

export function messageId(): string {
  return typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random()}`;
}

// Streamed output of one assistant response. Foreground and replayed background
// streams both reduce these onto the message they own.
export type AssistantEvent =
  | { type: 'delta'; text: string }
  | { type: 'reasoning'; text: string }
  | { type: 'truncated' }
  | { type: 'tool_start'; activity: ToolStartActivity }
  | { type: 'tool'; activity: ToolActivity }
  | { type: 'schedule_change'; before: string; after: string };

function appendResponseActivity(entries: ActivityEntry[], text: string): ActivityEntry[] {
  const last = entries[entries.length - 1];
  if (last?.kind === 'response') {
    return [...entries.slice(0, -1), { ...last, text: last.text + text }];
  }
  return [...entries, { kind: 'response', text }];
}

function appendReasoningActivity(entries: ActivityEntry[], text: string): ActivityEntry[] {
  const last = entries[entries.length - 1];
  // Consecutive reasoning belongs to one entry, so the order of work stays readable.
  if (last?.kind === 'reasoning') {
    return [...entries.slice(0, -1), { ...last, text: last.text + text }];
  }
  return [...entries, { kind: 'reasoning', text }];
}

// Concurrent calls finish in any order, so a result completes the start that shares its ID.
function finishToolActivity(entries: ActivityEntry[], result: ToolActivity): ActivityEntry[] {
  const runningIndex = entries.findIndex(entry => (
    entry.kind === 'tool'
    && entry.state === 'running'
    && (result.toolCallId === undefined ? entry.name === result.name : entry.toolCallId === result.toolCallId)
  ));
  const completed = { kind: 'tool' as const, ...result };
  if (runningIndex < 0) return [...entries, completed];
  return entries.map((entry, index) => (index === runningIndex ? completed : entry));
}

export function applyAssistantEvent<T extends ChatExportMessage>(message: T, event: AssistantEvent): T {
  const activity = message.activity ?? [];
  switch (event.type) {
    case 'delta':
      return {
        ...message,
        content: message.content + event.text,
        activity: appendResponseActivity(activity, event.text),
      };
    case 'reasoning':
      return { ...message, activity: appendReasoningActivity(activity, event.text) };
    case 'truncated':
      return { ...message, truncated: true };
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
  }
}

export function interruptRunningTools(entries: ActivityEntry[]): ActivityEntry[] {
  return entries.map(entry => (
    entry.kind === 'tool' && entry.state === 'running'
      ? { ...entry, state: 'interrupted' as const }
      : entry
  ));
}

export function resumeResponse<T extends ChatExportMessage>(message: T): T {
  return { ...message, status: 'pending', responseCompletedAt: undefined };
}

export function completeResponse<T extends ChatExportMessage>(message: T, completedAt = Date.now()): T {
  return { ...message, status: undefined, responseCompletedAt: completedAt };
}

export function failResponse<T extends ChatExportMessage>(message: T, fallbackText = ''): T {
  return {
    ...message,
    content: message.content || fallbackText,
    status: 'failed',
    responseCompletedAt: Date.now(),
    activity: interruptRunningTools(message.activity ?? []),
  };
}

export function staleResponse<T extends ChatExportMessage>(message: T, text: string): T {
  return { ...failResponse(message), content: text, activity: [{ kind: 'response', text }] };
}

// Insert steering before an empty answer. If output has already started, finish
// that segment and append the caller's new answer, preserving its run identity.
export function steerResponse<T extends ChatExportMessage & { id: string; runId?: string }>(
  messages: T[],
  assistantId: string,
  user: T,
  continuation?: T,
  completedId = assistantId,
): T[] {
  if (messages.some(message => message.id === user.id)) return messages;
  if (continuation) {
    return [
      ...messages.map(message => message.id === assistantId
        ? { ...completeResponse(message, continuation.responseStartedAt), id: completedId, runId: user.runId }
        : message),
      user,
      continuation,
    ];
  }
  const index = messages.findIndex(message => message.id === assistantId);
  return index < 0 ? [...messages, user] : [...messages.slice(0, index), user, ...messages.slice(index)];
}

// A stopped response keeps its partial output instead of gaining synthetic answer text.
export function stopResponse<T extends ChatExportMessage>(message: T): T {
  return {
    ...message,
    status: 'stopped',
    responseCompletedAt: Date.now(),
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
    case 'delta': case 'reasoning': case 'truncated': case 'tool_start': case 'tool':
      return event;
    case 'schedule_change': {
      const before = workingSchedule.current ?? browserSchedule.current;
      workingSchedule.current = event.scheduleYaml;
      return { type: 'schedule_change', before, after: event.scheduleYaml };
    }
    default: return null;
  }
}
