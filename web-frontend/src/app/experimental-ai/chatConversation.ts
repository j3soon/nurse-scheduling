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
import type { ChatMessage } from './chatTranscript';
import type { ActiveOptimization } from './optimizerEvents';
import { normalizeAiEndpoint, type ContextUsage } from './aiClient';
import { isCostSummary, isProviderCallCost, type CostSummary } from './costs';

export const AI_CONVERSATION_STORAGE_KEY = 'nurse-scheduling-ai-conversation';
export const HISTORY_RETENTION_MS = 7 * 24 * 60 * 60 * 1000;

export function clearStoredConversation(): void {
  try { window.sessionStorage.removeItem(AI_CONVERSATION_STORAGE_KEY); } catch { /* Storage can be disabled. */ }
}

export interface StoredChatConversation {
  lastActivityAt?: number;
  historyPending?: boolean;
  preserveBrowserSchedule?: boolean;
  sessionId: string;
  endpoint: string;
  expiresAt: number;
  retentionSeconds: number;
  messages: ChatMessage[];
  syncedSchedule: string;
  syncedBrowserSchedule?: string;
  // Run identity survives replacement replay and a later browser Undo.
  appliedScheduleRuns?: Record<string, string | null>;
  sessionEventId?: number;
  activeOptimization?: ActiveOptimization | null;
  backendVersion?: string;
  contextUsage?: ContextUsage | null;
  costSummary?: CostSummary | null;
  backgroundAssistantId?: string | null;
  trimmedHistoryCount?: number;
  pendingRequest?: {
    messageId: string; question: string; questionId: string; assistantId: string; activeAssistantId?: string; createdAt: number; uploading?: boolean;
    pendingFiles?: string[];
    selection?: import('./aiClient').ModelSelection;
  } | null;
}

function isOptionalStringArray(value: unknown): boolean {
  return value === undefined || (Array.isArray(value) && value.every(item => typeof item === 'string'));
}

function isActivityEntry(value: unknown): value is ActivityEntry {
  if (typeof value !== 'object' || value === null || !('kind' in value)) return false;
  if (value.kind === 'notice' || value.kind === 'response' || value.kind === 'reasoning' || value.kind === 'schedule-applied') {
    return 'text' in value && typeof value.text === 'string'
      && (!('context' in value) || value.context === 'complete' || value.context === 'omitted')
      && (!('notice' in value) || typeof value.notice === 'string')
      && (!('browserApplied' in value) || typeof value.browserApplied === 'boolean')
      && (!('runId' in value) || typeof value.runId === 'string');
  }
  if (value.kind === 'schedule-check') {
    return 'text' in value && typeof value.text === 'string' && 'ok' in value && typeof value.ok === 'boolean';
  }
  if (value.kind === 'schedule-change') {
    return 'before' in value && typeof value.before === 'string'
      && 'after' in value && typeof value.after === 'string';
  }
  if (value.kind === 'compaction') {
    return 'state' in value && typeof value.state === 'string'
      && ['running', 'completed', 'failed', 'interrupted', 'skipped'].includes(value.state)
      && 'reason' in value && (value.reason === 'threshold' || value.reason === 'overflow' || value.reason === 'manual')
      && 'text' in value && typeof value.text === 'string'
      && (!('summary' in value) || typeof value.summary === 'string')
      && (!('keepMessages' in value) || (Number.isSafeInteger(value.keepMessages) && (value.keepMessages as number) >= 0))
      && (!('characters' in value) || (Number.isSafeInteger(value.characters) && (value.characters as number) >= 0))
      && (!('step' in value) || (Number.isSafeInteger(value.step) && (value.step as number) >= 1))
      && (!('invalidated' in value) || typeof value.invalidated === 'boolean');
  }
  return value.kind === 'tool'
    && (!('state' in value) || value.state === 'preparing' || value.state === 'running' || value.state === 'interrupted')
    && (!('argumentsCharacters' in value) || (Number.isSafeInteger(value.argumentsCharacters) && (value.argumentsCharacters as number) >= 0))
    && (!('replayArguments' in value) || typeof value.replayArguments === 'string')
    && (!('endsRound' in value) || value.endsRound === true)
    && 'name' in value && typeof value.name === 'string'
    && 'arguments' in value && typeof value.arguments === 'string'
    && 'result' in value && typeof value.result === 'string'
    && 'ok' in value && typeof value.ok === 'boolean';
}

function isChatMessage(value: unknown): value is ChatMessage {
  if (typeof value !== 'object' || value === null) return false;
  const message = value as Partial<ChatMessage>;
  return typeof message.id === 'string'
    && (message.costSummary === undefined || isCostSummary(message.costSummary))
    && (message.providerCalls === undefined || (Array.isArray(message.providerCalls) && message.providerCalls.every(isProviderCallCost)))
    && (message.role === 'system' || message.role === 'user' || message.role === 'assistant' || message.role === 'optimizer')
    && typeof message.content === 'string'
    && (message.failureReason === undefined || typeof message.failureReason === 'string')
    && (message.source === undefined || message.source === 'app' || message.source === 'status' || message.source === 'optimizer')
    && (message.historyIndex === undefined || Number.isSafeInteger(message.historyIndex))
    && (message.title === undefined || typeof message.title === 'string')
    && (message.activity === undefined
      || (Array.isArray(message.activity) && message.activity.every(isActivityEntry)))
    && (message.status === undefined || message.status === 'pending' || message.status === 'failed' || message.status === 'stopped')
    && (message.createdAt === undefined || Number.isFinite(message.createdAt))
    && (message.responseStartedAt === undefined || Number.isFinite(message.responseStartedAt))
    && (message.responseCompletedAt === undefined || Number.isFinite(message.responseCompletedAt))
    && isOptionalStringArray(message.unsentFiles)
    && (message.requestId === undefined || typeof message.requestId === 'string')
    && (message.request === undefined || (typeof message.request === 'object' && message.request !== null
      && typeof message.request.id === 'string' && typeof message.request.question === 'string'
      && typeof message.request.questionId === 'string' && typeof message.request.assistantId === 'string'
      && (message.request.activeAssistantId === undefined || typeof message.request.activeAssistantId === 'string')
      && typeof message.request.active === 'boolean'
      && (message.request.uploading === undefined || typeof message.request.uploading === 'boolean')
      && isOptionalStringArray(message.request.pendingFiles)))
    && (message.downloadId === undefined || typeof message.downloadId === 'string')
    && (message.optimizerJob === undefined || (message.optimizerJob !== null
      && typeof message.optimizerJob.jobId === 'string'
      && typeof message.optimizerJob.downloadable === 'boolean'
    ));
}

export function readStoredConversation(): StoredChatConversation | null {
  try {
    const raw = window.sessionStorage.getItem(AI_CONVERSATION_STORAGE_KEY);
    const conversation = raw === null ? null : parseStoredConversation(JSON.parse(raw));
    if (conversation?.lastActivityAt !== undefined && conversation.lastActivityAt + HISTORY_RETENTION_MS <= Date.now()) {
      window.sessionStorage.removeItem(AI_CONVERSATION_STORAGE_KEY);
      return null;
    }
    return conversation;
  } catch {
    return null;
  }
}

export function parseStoredConversation(input: unknown): StoredChatConversation | null {
  try {
    if (typeof input !== 'object' || input === null) return null;
    const value = { ...input } as Partial<StoredChatConversation>;
    if (
      (value.lastActivityAt !== undefined && !Number.isFinite(value.lastActivityAt))
      || (value.historyPending !== undefined && typeof value.historyPending !== 'boolean')
      || (value.preserveBrowserSchedule !== undefined && typeof value.preserveBrowserSchedule !== 'boolean')
      || typeof value.sessionId !== 'string'
      || !value.sessionId
      || typeof value.endpoint !== 'string'
      || !(value.endpoint === '/ai' || normalizeAiEndpoint(value.endpoint))
      || !Number.isFinite(value.expiresAt)
      || !Number.isInteger(value.retentionSeconds)
      || (value.retentionSeconds ?? 0) <= 0
      || !Array.isArray(value.messages)
      || !value.messages.every(isChatMessage)
      || (value.costSummary != null && !isCostSummary(value.costSummary))
      || (value.backendVersion !== undefined && typeof value.backendVersion !== 'string')
      || (value.contextUsage != null && (!Number.isSafeInteger(value.contextUsage.usedChars)
        || value.contextUsage.usedChars < 0 || !Number.isSafeInteger(value.contextUsage.maxChars)
        || value.contextUsage.maxChars <= 0 || value.contextUsage.usedChars > value.contextUsage.maxChars
        || (value.contextUsage.usedTokens !== undefined && !Number.isSafeInteger(value.contextUsage.usedTokens))
        || (value.contextUsage.maxTokens !== undefined && !Number.isSafeInteger(value.contextUsage.maxTokens))
        || (value.contextUsage.estimated !== undefined && typeof value.contextUsage.estimated !== 'boolean')))
      || (value.sessionEventId !== undefined
        && (!Number.isSafeInteger(value.sessionEventId) || value.sessionEventId < 0))
      || (value.trimmedHistoryCount !== undefined
        && (!Number.isSafeInteger(value.trimmedHistoryCount) || value.trimmedHistoryCount < 0))
      || (value.activeOptimization !== undefined && value.activeOptimization !== null && (
        typeof value.activeOptimization.jobId !== 'string'
        || typeof value.activeOptimization.state !== 'string'
        || typeof value.activeOptimization.terminal !== 'boolean'
        || typeof value.activeOptimization.downloadable !== 'boolean'
        || (value.activeOptimization.points !== undefined && (
          !Array.isArray(value.activeOptimization.points)
          || !value.activeOptimization.points.every(point => (
            typeof point.currentBestScore === 'number' && Number.isFinite(point.currentBestScore)
            && typeof point.elapsedSeconds === 'number' && Number.isFinite(point.elapsedSeconds)
          ))
        ))
      ))
      || typeof value.syncedSchedule !== 'string'
      || (value.syncedBrowserSchedule !== undefined && typeof value.syncedBrowserSchedule !== 'string')
      || (value.appliedScheduleRuns !== undefined && (value.appliedScheduleRuns === null
        || typeof value.appliedScheduleRuns !== 'object' || Array.isArray(value.appliedScheduleRuns)
        || !Object.values(value.appliedScheduleRuns).every(notice => notice === null || typeof notice === 'string')))
      || (value.backgroundAssistantId !== undefined && value.backgroundAssistantId !== null
        && typeof value.backgroundAssistantId !== 'string')
    ) return null;
    const pending = value.pendingRequest;
    if (pending != null) {
      if (typeof pending.messageId !== 'string' || !pending.messageId || typeof pending.question !== 'string'
        || typeof pending.questionId !== 'string' || typeof pending.assistantId !== 'string'
        || (pending.activeAssistantId !== undefined && typeof pending.activeAssistantId !== 'string')
        || !Number.isFinite(pending.createdAt) || (pending.uploading !== undefined && typeof pending.uploading !== 'boolean')
        || !isOptionalStringArray(pending.pendingFiles)) return null;
      value.messages = value.messages.map(message => message.id === pending.questionId
        ? { ...message, request: { selection: pending.selection, id: pending.messageId, question: pending.question, questionId: pending.questionId,
          assistantId: pending.assistantId, activeAssistantId: pending.activeAssistantId, active: true, uploading: pending.uploading,
          pendingFiles: pending.pendingFiles } } : message);
    }
    return {
      ...value,
      endpoint: value.endpoint === '/ai' ? value.endpoint : normalizeAiEndpoint(value.endpoint),
    } as StoredChatConversation;
  } catch {
    return null;
  }
}
