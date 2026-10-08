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

import type { ChatExportMessage } from './chatExport';
import type { ModelInput, OptimizationActivity } from './aiClient';
import { type AssistantEvent, applyAssistantEvent, completeResponse, interruptRunningTools, resumeResponse } from './assistantEvents';

export interface ChatMessage extends ChatExportMessage {
  id: string;
  runId?: string;
  // A generated ZIP retained by the session for this answer.
  downloadId?: string;
  // Absolute history position of an app event, so a retried run does not show it twice.
  historyIndex?: number;
  retry?: {
    question: string;
    requiresAttachments: boolean;
  };
  optimizerJob?: Pick<OptimizationActivity, 'jobId' | 'downloadable'>;
}

export function createResponse(id: string, startedAt: number, runId?: string): ChatMessage {
  return { id, runId, role: 'assistant', content: '', status: 'pending', responseStartedAt: startedAt };
}

// Reconnect resumes the existing answer rather than appending a second one.
export function beginResponse(messages: ChatMessage[], response: ChatMessage): ChatMessage[] {
  return messages.some(message => message.id === response.id)
    ? messages.map(message => message.id === response.id ? resumeResponse(message) : message)
    : [...messages, response];
}

export function applyResponseEvent(
  messages: ChatMessage[], assistantId: string, event: AssistantEvent, occurredAt: number,
): ChatMessage[] {
  return messages.map(message => message.id === assistantId ? applyAssistantEvent(message, event, occurredAt) : message);
}

// A recovery snapshot replaces only its runs. Extra IDs cover foreground output
// created before POST acknowledged its run, while the original prompt stays.
// Replayed output returns to its original position, before any later question:
// `response` takes the place of the first replaced message, and a background
// answer, whose ID is its run ID, stays as an empty answer that the replay fills.
export function resetRunMessages(
  messages: ChatMessage[], runIds: readonly string[], response?: ChatMessage, messageIds?: ReadonlySet<string>,
): ChatMessage[] {
  const result: ChatMessage[] = [];
  let placed = response === undefined;
  for (const message of messages) {
    const runId = message.runId ?? message.id;
    if (!runIds.includes(runId) && !messageIds?.has(message.id)) {
      result.push(message);
    } else if (!placed) {
      result.push(response!);
      placed = true;
    } else if (response === undefined && message.role === 'assistant' && message.id === runId
      && !result.some(kept => kept.id === message.id)) {
      result.push(createResponse(message.id, message.responseStartedAt ?? Date.now(), message.runId));
    }
  }
  return placed ? result : [...result, response!];
}

// A pending answer stopped with the old page, except the one a resumed request reattaches to.
export function restoreTranscript(messages: ChatMessage[], resumedId?: string): ChatMessage[] {
  return messages.map(message => message.status === 'pending' && message.id !== resumedId
    ? { ...message, status: 'failed', activity: interruptRunningTools(message.activity ?? []) }
    : message);
}

// Insert steering before an empty answer. Otherwise finish that segment and
// append a fresh response. Callers supply IDs and timestamps without doing I/O here.
export function steerResponse(
  messages: ChatMessage[], assistantId: string, user: ChatMessage, startedAt: number,
  continuationId?: string, completedId = assistantId,
): ChatMessage[] {
  if (messages.some(message => message.id === user.id)) return messages;
  if (continuationId) {
    return [
      ...messages.map(message => message.id === assistantId
        ? { ...completeResponse(message, startedAt), id: completedId, runId: user.runId }
        : message),
      user,
      createResponse(continuationId, startedAt, user.runId),
    ];
  }
  const index = messages.findIndex(message => message.id === assistantId);
  return index < 0 ? [...messages, user] : [...messages.slice(0, index), user, ...messages.slice(index)];
}

// Show the request messages added since the last reply, in the order the model receives them:
// a changed system prompt, app events, the question, and a status message just before the reply.
export function applyModelInput(
  messages: ChatMessage[],
  input: ModelInput,
  run: { questionId: string | null; assistantId: string },
  systemId: string,
): ChatMessage[] {
  // History never keeps a status message, so only the latest request's status stays visible.
  const result = messages.filter(message => message.source !== 'status');
  const known = new Set(result.map(message => message.historyIndex));
  const lastSystem = [...result].reverse().find(message => message.role === 'system');
  const before: ChatMessage[] = lastSystem?.content === input.system
    ? []
    : [{ id: systemId, role: 'system', content: input.system }];
  let status: ChatMessage | null = null;
  let questionText: string | null = null;
  let optimizerText: string | null = null;
  input.messages.forEach(entry => {
    if (entry.kind === 'app' && !known.has(entry.index)) {
      before.push({
        id: `history-${entry.index}`, role: 'user', source: 'app', title: entry.title, historyIndex: entry.index, content: entry.content,
      });
    } else if (entry.kind === 'status') {
      status = { id: `status-${run.assistantId}`, role: 'user', source: 'status', title: entry.title, content: entry.content };
    } else if (entry.kind === 'question') {
      questionText = entry.content;
    } else if (entry.kind === 'optimizer') {
      optimizerText = entry.content;
    }
  });
  let assistantIndex = result.findIndex(message => message.id === run.assistantId);
  if (assistantIndex < 0) return messages;
  let questionIndex = run.questionId === null ? -1 : result.findIndex(message => message.id === run.questionId);
  if (questionIndex >= 0 && questionText !== null) {
    result[questionIndex] = { ...result[questionIndex], content: questionText };
  }
  if (optimizerText !== null) {
    // The optimizer notice keeps the run summary. The model receives its own user-role optimizer message.
    const optimizerId = `optimizer-input-${run.assistantId}`;
    questionIndex = result.findIndex(message => message.id === optimizerId);
    if (questionIndex >= 0) {
      result[questionIndex] = { ...result[questionIndex], content: optimizerText };
    } else {
      result.splice(assistantIndex, 0, { id: optimizerId, role: 'user', source: 'optimizer', content: optimizerText });
      questionIndex = assistantIndex;
      assistantIndex += 1;
    }
  }
  const insertAt = questionIndex >= 0 ? questionIndex : assistantIndex;
  result.splice(insertAt, 0, ...before);
  assistantIndex += before.length;
  if (status !== null) result.splice(assistantIndex, 0, status);
  return result;
}

// A retried run replaces the failed question, status, and reply. App events stay in history.
export function removeFailedRun(messages: ChatMessage[], failedId: string): ChatMessage[] {
  const failedIndex = messages.findIndex(message => message.id === failedId);
  if (failedIndex < 0) return messages;
  let start = failedIndex;
  if (messages[start - 1]?.source === 'status') start -= 1;
  if (messages[start - 1]?.role === 'user' && messages[start - 1]?.source === undefined) start -= 1;
  return [...messages.slice(0, start), ...messages.slice(failedIndex + 1)];
}
