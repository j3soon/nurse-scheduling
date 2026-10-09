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

import { applyAssistantEvent, toAssistantEvent } from './assistantEvents';
import { applyModelInput, type ChatMessage } from './chatTranscript';
import { decodeEvent } from './aiClient';
import { applyOptimizationEvent, appendOptimizationResult, type ActiveOptimization } from './optimizerEvents';
import { buildHtmlChatExport, buildMarkdownChatExport, type ChatExportFormat, type ChatExportMetadata } from './chatExport';

export interface SavedChatSnapshot {
  schema_version: 1;
  session_id: string;
  snapshot_at: number;
  frontend_version: string;
  metadata: { endpoint?: string; backend_version?: string; uploaded_files?: { filename: string; bytes: number }[] };
  pending_proposal_diff: string | null;
  runs: { id: string; kind: string; status: string; prompt: string; started_at: number; finished_at: number | null }[];
  events: { type: string; data: Record<string, unknown>; occurred_at: number }[];
}

const record = (value: unknown): value is Record<string, unknown> => typeof value === 'object' && value !== null && !Array.isArray(value);
const timestamp = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value) && value >= 0;

export function parseSavedChatSnapshot(value: unknown): SavedChatSnapshot {
  if (!record(value) || value.schema_version !== 1 || typeof value.session_id !== 'string'
    || !timestamp(value.snapshot_at) || typeof value.frontend_version !== 'string' || !record(value.metadata)
    || (value.pending_proposal_diff !== null && typeof value.pending_proposal_diff !== 'string')
    || !Array.isArray(value.runs) || !value.runs.every(run => record(run) && typeof run.id === 'string'
      && typeof run.kind === 'string' && typeof run.status === 'string' && typeof run.prompt === 'string'
      && timestamp(run.started_at) && (run.finished_at === null || timestamp(run.finished_at)))
    || !Array.isArray(value.events) || !value.events.every(event => record(event) && typeof event.type === 'string'
      && record(event.data) && timestamp(event.occurred_at))
    || (value.metadata.endpoint !== undefined && typeof value.metadata.endpoint !== 'string')
    || (value.metadata.backend_version !== undefined && typeof value.metadata.backend_version !== 'string')
    || (value.metadata.uploaded_files !== undefined && (!Array.isArray(value.metadata.uploaded_files)
      || !value.metadata.uploaded_files.every(file => record(file) && typeof file.filename === 'string' && timestamp(file.bytes))))) {
    throw new Error('The AI backend returned an invalid saved chat snapshot.');
  }
  return value as unknown as SavedChatSnapshot;
}

export function projectSavedChat(snapshot: SavedChatSnapshot): { messages: ChatMessage[]; metadata: ChatExportMetadata } {
  let messages: ChatMessage[] = [];
  let activeOptimization: ActiveOptimization | null = null;
  const runs = new Map(snapshot.runs.map(run => [run.id, run]));
  const turns = new Map<string, { assistantId: string; questionId: string | null; segment: number; workingSchedule: { current: string | null }; schedule: { current: string } }>();
  const ensureTurn = (runId: string, at: number) => {
    let turn = turns.get(runId);
    if (turn) return turn;
    const run = runs.get(runId);
    const questionId = run?.kind === 'foreground' ? `question-${runId}` : null;
    if (questionId !== null) messages.push({ id: questionId, role: 'user', content: run?.prompt ?? '', createdAt: run?.started_at ?? at });
    turn = { assistantId: `assistant-${runId}`, questionId, segment: 0, workingSchedule: { current: null }, schedule: { current: '' } };
    messages.push({ id: turn.assistantId, role: 'assistant', content: '', status: 'pending', responseStartedAt: run?.started_at ?? at });
    turns.set(runId, turn);
    return turn;
  };

  for (const raw of snapshot.events) {
    for (const event of decodeEvent(raw.type, raw.data)) {
      if (event.type === 'optimization' || event.type === 'optimization_progress') {
        activeOptimization = applyOptimizationEvent(activeOptimization, event);
        if (event.type === 'optimization' && event.activity.terminal) messages = appendOptimizationResult(messages, event.activity, raw.occurred_at);
        continue;
      }
      if (!event.runId || event.type === 'run_context') continue;
      const turn = ensureTurn(event.runId, raw.occurred_at);
      if (event.type === 'model_input') {
        if (typeof raw.data.schedule_yaml === 'string') turn.schedule.current = raw.data.schedule_yaml;
        messages = applyModelInput(messages, event.input, turn);
      } else if (event.type === 'steering') {
        messages = messages.map(message => message.id === turn.assistantId ? applyAssistantEvent(message, { type: 'done' }, raw.occurred_at) : message);
        turn.segment += 1;
        turn.questionId = `question-${event.messageId}`;
        turn.assistantId = `assistant-${event.runId}-${turn.segment}`;
        messages.push({ id: turn.questionId, role: 'user', content: event.message, createdAt: raw.occurred_at });
        messages.push({ id: turn.assistantId, role: 'assistant', content: '', status: 'pending', responseStartedAt: raw.occurred_at });
      } else if (event.type === 'download') {
        messages = messages.map(message => message.id === turn.assistantId ? { ...message, downloadId: event.downloadId } : message);
      } else {
        const assistantEvent = ['done', 'stopped', 'error', 'stale'].includes(event.type)
          ? event as Extract<typeof event, { type: 'done' | 'stopped' | 'error' | 'stale' }>
          : toAssistantEvent(event, turn.workingSchedule, turn.schedule);
        if (assistantEvent !== null) messages = messages.map(message => message.id === turn.assistantId
          ? applyAssistantEvent(message, assistantEvent, raw.occurred_at) : message);
      }
    }
  }
  for (const run of snapshot.runs) {
    const turn = ensureTurn(run.id, run.started_at);
    messages = messages.map(message => {
      if (message.id !== turn.assistantId || message.status !== 'pending' || run.status === 'running') return message;
      const type = run.status === 'cancelled' ? 'stopped' : run.status === 'completed' ? 'done' : 'error';
      return applyAssistantEvent(message, type === 'error' ? { type, message: 'This response did not complete.' } : { type }, run.finished_at ?? snapshot.snapshot_at);
    });
  }
  return {
    messages,
    metadata: {
      endpoint: snapshot.metadata.endpoint ?? 'unknown', exportedAt: new Date(snapshot.snapshot_at),
      frontendVersion: snapshot.frontend_version, backendVersion: snapshot.metadata.backend_version,
      uploadedFiles: snapshot.metadata.uploaded_files, pendingProposalDiff: snapshot.pending_proposal_diff ?? undefined,
      runningOptimization: activeOptimization === null ? undefined : {
        jobId: activeOptimization.jobId, state: activeOptimization.state,
        solver: activeOptimization.request?.solver, timeoutSeconds: activeOptimization.request?.timeoutSeconds,
      },
      timeZone: 'UTC',
    },
  };
}

export function buildSavedChatExport(value: unknown, format: ChatExportFormat): string {
  const { messages, metadata } = projectSavedChat(parseSavedChatSnapshot(value));
  return format === 'html' ? buildHtmlChatExport(messages, metadata) : buildMarkdownChatExport(messages, metadata);
}
