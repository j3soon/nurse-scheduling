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
import { messageId } from './assistantEvents';

export interface ChatMessage extends ChatExportMessage {
  id: string;
  requestId?: string;
  request?: { id: string; question: string; questionId: string; assistantId: string; activeAssistantId?: string; active: boolean; uploading?: boolean };
  downloadId?: string;
  // Absolute history position of an app event, so a retried turn does not show it twice.
  historyIndex?: number;
  runId?: string;
  retry?: {
    question: string;
    requiresAttachments: boolean;
  };
  optimizerJob?: Pick<OptimizationActivity, 'jobId' | 'downloadable'>;
}

// Show the request messages added since the last reply, in the order the model receives them:
// a changed system prompt, app events, the question, and a status message just before the reply.
export function applyModelInput(
  messages: ChatMessage[],
  input: ModelInput,
  turn: { questionId: string | null; assistantId: string },
): ChatMessage[] {
  const statusId = `status-${turn.assistantId}`;
  // History never keeps a status message, so only the latest request's status stays visible.
  const result = messages.filter(message => message.source !== 'status');
  const known = new Set(result.map(message => message.historyIndex));
  const lastSystem = [...result].reverse().find(message => message.role === 'system');
  const before: ChatMessage[] = lastSystem?.content === input.system
    ? []
    : [{ id: messageId(), role: 'system', content: input.system }];
  let status: ChatMessage | null = null;
  let questionText: string | null = null;
  let optimizerText: string | null = null;
  input.messages.forEach(entry => {
    if (entry.kind === 'app' && !known.has(entry.index)) {
      before.push({
        id: `history-${entry.index}`, role: 'user', source: 'app', title: entry.title, historyIndex: entry.index, content: entry.content,
      });
    } else if (entry.kind === 'status') {
      status = { id: statusId, role: 'user', source: 'status', title: entry.title, content: entry.content };
    } else if (entry.kind === 'question') {
      questionText = entry.content;
    } else if (entry.kind === 'optimizer') {
      optimizerText = entry.content;
    }
  });
  let assistantIndex = result.findIndex(message => message.id === turn.assistantId);
  if (assistantIndex < 0) return messages;
  let questionIndex = turn.questionId === null ? -1 : result.findIndex(message => message.id === turn.questionId);
  if (questionIndex >= 0 && questionText !== null) {
    result[questionIndex] = { ...result[questionIndex], content: questionText };
  }
  if (optimizerText !== null) {
    // The optimizer notice keeps the run summary. The model receives its own user-role optimizer message.
    const optimizerId = `optimizer-input-${turn.assistantId}`;
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
