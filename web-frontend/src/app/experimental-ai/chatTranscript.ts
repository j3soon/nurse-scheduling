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
import type { OptimizationActivity } from './aiClient';
import { type AssistantEvent, applyAssistantEvent, completeResponse, interruptRunningTools, resumeResponse } from './assistantEvents';

export interface ChatMessage extends ChatExportMessage {
  id: string;
  runId?: string;
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
export function resetRunMessages(
  messages: ChatMessage[], runIds: readonly string[], response?: ChatMessage, messageIds?: ReadonlySet<string>,
): ChatMessage[] {
  const retained = messages.filter(message => (
    !runIds.includes(message.runId ?? message.id) && !messageIds?.has(message.id)
  ));
  return response ? [...retained, response] : retained;
}

export function restoreTranscript(messages: ChatMessage[]): ChatMessage[] {
  return messages.map(message => message.status === 'pending'
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
