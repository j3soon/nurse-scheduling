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

import {
  buildAuthHeaders,
  parseAuthRequirement,
  type AuthRequirement,
} from '@/utils/backendAuth';
import type { OptimizationProgressPoint } from '@/components/OptimizationProgressChart';

export interface ToolActivity {
  name: string;
  arguments: string;
  result: string;
  ok: boolean;
}

export type ToolStartActivity = Pick<ToolActivity, 'name' | 'arguments'>;

export interface OptimizationActivity {
  jobId: string;
  state: string;
  terminal: boolean;
  downloadable: boolean;
}

export interface OptimizationProgressActivity {
  jobId: string;
  point: OptimizationProgressPoint;
}

export interface StreamCallbacks {
  lastEventId?: number;
  onEventId?: (id: number) => void;
  onTurnStart?: (messageId: string, trigger: string) => void;
  onDelta: (text: string) => void;
  onReasoning?: (text: string) => void;
  onToolStart?: (activity: ToolStartActivity) => void;
  onTool?: (activity: ToolActivity) => void;
  onSteering?: (messageId: string, message: string) => void;
  onScheduleChange?: (scheduleYaml: string) => void;
  onProposal?: (diff: string) => void;
  onOptimization?: (activity: OptimizationActivity) => void;
  onOptimizationProgress?: (activity: OptimizationProgressActivity) => void;
  onDone?: (messageId?: string) => void;
  onStopped?: (messageId?: string) => void;
  onStale?: (message: string) => void;
  onHistoryTrimmed?: (dropped: number) => void;
  onError?: (message: string) => void;
}

export interface AiCapabilities {
  auth: AuthRequirement | null;
  session_retention_seconds: number;
  file_attachments: {
    enabled: boolean;
    max_files: number;
    max_bytes_per_file: number;
  };
}

export interface MessageAttachments {
  files?: File[];
}

interface SessionResponse {
  id: string;
}

interface SessionStatusResponse {
  expires_in_seconds: number;
}

interface SsePayload {
  text?: unknown;
  message?: unknown;
  name?: unknown;
  diff?: unknown;
  arguments?: unknown;
  result?: unknown;
  ok?: unknown;
  schedule_yaml?: unknown;
  message_id?: unknown;
  trigger?: unknown;
  job_id?: unknown;
  state?: unknown;
  terminal?: unknown;
  downloadable?: unknown;
  progress?: unknown;
  dropped?: unknown;
}

export class AiHttpError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = 'AiHttpError';
  }
}

export class AiStaleTurnError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'AiStaleTurnError';
  }
}

export const PRODUCTION_AI_API_URL = 'https://api.nursescheduling.org/ai';
export const LOCAL_AI_API_URL = 'http://localhost:8001';
export const DEFAULT_SESSION_RETENTION_SECONDS = 48 * 60 * 60;

export function getAiBaseUrl(): string {
  const configuredUrl = process.env.NEXT_PUBLIC_AI_API_URL?.trim().replace(/\/$/, '');
  if (configuredUrl) return configuredUrl;
  return PRODUCTION_AI_API_URL;
}

export const SAME_ORIGIN_AI_API_PATH = '/ai';

export function isOfficialAiEndpoint(endpoint: string): boolean {
  if (endpoint === SAME_ORIGIN_AI_API_PATH) return true;
  return normalizeAiEndpoint(endpoint) === PRODUCTION_AI_API_URL;
}

export function normalizeAiEndpoint(endpoint: string): string {
  const trimmed = endpoint.trim();
  if (!trimmed) return '';
  const withScheme = /^[a-zA-Z][a-zA-Z0-9+.-]*:\/\//.test(trimmed)
    ? trimmed
    : `${/^(localhost|127\.0\.0\.1|\[::1\])(?::|\/|$)/i.test(trimmed) ? 'http' : 'https'}://${trimmed.replace(/^\/+/, '')}`;
  try {
    const url = new URL(withScheme);
    if (url.protocol !== 'http:' && url.protocol !== 'https:') return '';
    return url.toString().replace(/\/+$/, '');
  } catch {
    return '';
  }
}

async function responseError(response: Response): Promise<Error> {
  try {
    const body = await response.json() as { detail?: unknown };
    if (typeof body.detail === 'string') return new AiHttpError(body.detail, response.status);
  } catch {
    // Fall back to a stable error when the response is not JSON.
  }
  return new AiHttpError(`The AI backend returned HTTP ${response.status}.`, response.status);
}

function authorizedHeaders(
  token: string | null,
  headers?: Record<string, string>,
): Record<string, string> | undefined {
  if (token === null && headers === undefined) return undefined;
  return { ...headers, ...buildAuthHeaders(token) };
}

export async function getCapabilities(signal?: AbortSignal, endpoint = getAiBaseUrl()): Promise<AiCapabilities> {
  const response = await fetch(`${endpoint}/capabilities`, {
    credentials: 'include',
    signal,
  });
  if (!response.ok) throw await responseError(response);

  const body = await response.json() as Partial<AiCapabilities>;
  const auth = parseAuthRequirement(body.auth);
  const sessionRetention = body.session_retention_seconds ?? DEFAULT_SESSION_RETENTION_SECONDS;
  const files = body.file_attachments;
  if (
    !Number.isInteger(sessionRetention)
    || sessionRetention <= 0
    || files?.enabled !== true
    || !Number.isInteger(files.max_files)
    || files.max_files <= 0
    || !Number.isInteger(files.max_bytes_per_file)
    || files.max_bytes_per_file <= 0
  ) {
    throw new Error('The AI backend returned invalid capabilities.');
  }
  return { ...body, auth, session_retention_seconds: sessionRetention } as AiCapabilities;
}

export async function createSession(
  scheduleYaml: string,
  authToken: string | null,
  endpoint = getAiBaseUrl(),
): Promise<string> {
  const response = await fetch(`${endpoint}/sessions`, {
    method: 'POST',
    credentials: 'include',
    headers: authorizedHeaders(authToken, { 'Content-Type': 'application/json' }),
    body: JSON.stringify({ schedule_yaml: scheduleYaml }),
  });
  if (!response.ok) throw await responseError(response);

  const body = await response.json() as Partial<SessionResponse>;
  if (typeof body.id !== 'string' || !body.id) {
    throw new Error('The AI backend returned an invalid session.');
  }
  return body.id;
}

export async function getSessionStatus(
  sessionId: string,
  authToken: string | null,
  endpoint = getAiBaseUrl(),
): Promise<number> {
  const response = await fetch(`${endpoint}/sessions/${encodeURIComponent(sessionId)}`, {
    credentials: 'include',
    headers: authorizedHeaders(authToken),
  });
  if (!response.ok) throw await responseError(response);

  const body = await response.json() as Partial<SessionStatusResponse>;
  if (!Number.isInteger(body.expires_in_seconds) || (body.expires_in_seconds ?? 0) <= 0) {
    throw new Error('The AI backend returned an invalid session status.');
  }
  return body.expires_in_seconds as number;
}

function consumeEvent(block: string, callbacks: StreamCallbacks): void {
  const lines = block.split('\n');
  const eventId = Number(lines.find(line => line.startsWith('id:'))?.slice('id:'.length).trim());
  const eventType = lines.find(line => line.startsWith('event:'))?.slice('event:'.length).trim() ?? 'message';
  const rawData = lines
    .filter(line => line.startsWith('data:'))
    .map(line => line.slice('data:'.length).trimStart())
    .join('\n');
  if (!rawData) return;

  let payload: SsePayload;
  try {
    payload = JSON.parse(rawData) as SsePayload;
  } catch {
    throw new Error('The AI backend returned an invalid stream.');
  }

  // Acknowledge before dispatching, so a handler that throws cannot make a
  // replayed stream repeat the same event after every reconnect.
  if (Number.isSafeInteger(eventId) && eventId > 0) callbacks.onEventId?.(eventId);

  if (eventType === 'turn_start' && typeof payload.message_id === 'string') {
    callbacks.onTurnStart?.(
      payload.message_id,
      typeof payload.trigger === 'string' ? payload.trigger : 'background work',
    );
  } else if (eventType === 'delta' && typeof payload.text === 'string') {
    callbacks.onDelta(payload.text);
  } else if (eventType === 'reasoning' && typeof payload.text === 'string') {
    callbacks.onReasoning?.(payload.text);
  } else if (eventType === 'tool_start' && typeof payload.name === 'string') {
    callbacks.onToolStart?.({
      name: payload.name,
      arguments: typeof payload.arguments === 'string' ? payload.arguments : '',
    });
  } else if (eventType === 'tool' && typeof payload.name === 'string') {
    callbacks.onTool?.({
      name: payload.name,
      arguments: typeof payload.arguments === 'string' ? payload.arguments : '',
      result: typeof payload.result === 'string' ? payload.result : '',
      ok: payload.ok !== false,
    });
  } else if (
    eventType === 'steering'
    && typeof payload.message_id === 'string'
    && typeof payload.message === 'string'
  ) {
    callbacks.onSteering?.(payload.message_id, payload.message);
  } else if (eventType === 'schedule_change') {
    if (typeof payload.schedule_yaml !== 'string') {
      throw new Error('The AI backend returned an invalid schedule change.');
    }
    callbacks.onScheduleChange?.(payload.schedule_yaml);
  } else if (eventType === 'proposal' && typeof payload.diff === 'string') {
    callbacks.onProposal?.(payload.diff);
  } else if (
    eventType === 'optimization'
    && typeof payload.job_id === 'string'
    && typeof payload.state === 'string'
    && typeof payload.terminal === 'boolean'
    && typeof payload.downloadable === 'boolean'
  ) {
    callbacks.onOptimization?.({
      jobId: payload.job_id,
      state: payload.state,
      terminal: payload.terminal,
      downloadable: payload.downloadable,
    });
  } else if (eventType === 'optimization_progress' && typeof payload.job_id === 'string') {
    const point = payload.progress as Record<string, unknown> | null | undefined;
    if (
      typeof point === 'object' && point !== null
      && typeof point.currentBestScore === 'number' && Number.isFinite(point.currentBestScore)
      && typeof point.elapsedSeconds === 'number' && Number.isFinite(point.elapsedSeconds)
      && point.elapsedSeconds >= 0
    ) {
      callbacks.onOptimizationProgress?.({
        jobId: payload.job_id,
        point: {
          currentBestScore: point.currentBestScore,
          elapsedSeconds: point.elapsedSeconds,
          commentCount: typeof point.commentCount === 'number' ? point.commentCount : null,
          solutionIndex: typeof point.solutionIndex === 'number' ? point.solutionIndex : null,
          source: typeof point.source === 'string' ? point.source : undefined,
        },
      });
    }
  } else if (eventType === 'done') {
    callbacks.onDone?.(typeof payload.message_id === 'string' ? payload.message_id : undefined);
  } else if (eventType === 'stopped') {
    callbacks.onStopped?.(typeof payload.message_id === 'string' ? payload.message_id : undefined);
  } else if (eventType === 'stale') {
    const message = typeof payload.message === 'string' ? payload.message : 'The AI response became stale.';
    if (callbacks.onStale) callbacks.onStale(message);
    else throw new AiStaleTurnError(message);
  } else if (eventType === 'history_trimmed') {
    const dropped = payload.dropped;
    if (typeof dropped === 'number' && Number.isInteger(dropped) && dropped > 0) {
      callbacks.onHistoryTrimmed?.(dropped);
    }
  } else if (eventType === 'error') {
    const message = typeof payload.message === 'string' ? payload.message : 'The AI response failed.';
    if (callbacks.onError) callbacks.onError(message);
    else throw new Error(message);
  }
}

export async function streamMessage(
  sessionId: string,
  message: string,
  callbacks: StreamCallbacks,
  signal: AbortSignal,
  authToken: string | null,
  attachments: MessageAttachments = {},
  endpoint = getAiBaseUrl(),
): Promise<void> {
  const files = attachments.files ?? [];
  let body: BodyInit;
  let headers: Record<string, string> | undefined;
  if (files.length > 0) {
    const form = new FormData();
    form.append('message', message);
    files.forEach(file => form.append('files', file, file.name));
    body = form;
  } else {
    headers = { 'Content-Type': 'application/json' };
    body = JSON.stringify({ message });
  }

  const response = await fetch(`${endpoint}/sessions/${encodeURIComponent(sessionId)}/messages`, {
    method: 'POST',
    credentials: 'include',
    headers: authorizedHeaders(authToken, headers),
    body,
    signal,
  });
  if (!response.ok) throw await responseError(response);
  await consumeStream(response, callbacks);
}

async function consumeStream(response: Response, callbacks: StreamCallbacks): Promise<void> {
  if (!response.body) throw new Error('The AI backend returned an empty stream.');

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done }).replace(/\r\n/g, '\n');

    let boundary = buffer.indexOf('\n\n');
    while (boundary >= 0) {
      consumeEvent(buffer.slice(0, boundary), callbacks);
      buffer = buffer.slice(boundary + 2);
      boundary = buffer.indexOf('\n\n');
    }

    if (done) break;
  }

  if (buffer.trim()) consumeEvent(buffer, callbacks);
}

export async function streamSessionEvents(
  sessionId: string,
  callbacks: StreamCallbacks,
  signal: AbortSignal,
  authToken: string | null,
  endpoint = getAiBaseUrl(),
): Promise<void> {
  const response = await fetch(`${endpoint}/sessions/${encodeURIComponent(sessionId)}/events`, {
    method: 'GET',
    credentials: 'include',
    headers: authorizedHeaders(
      authToken,
      callbacks.lastEventId ? { 'Last-Event-ID': String(callbacks.lastEventId) } : undefined,
    ),
    signal,
  });
  if (!response.ok) throw await responseError(response);
  await consumeStream(response, callbacks);
}

export async function queueMessage(
  sessionId: string,
  messageId: string,
  message: string,
  authToken: string | null,
  endpoint = getAiBaseUrl(),
): Promise<void> {
  const response = await fetch(`${endpoint}/sessions/${encodeURIComponent(sessionId)}/messages/queue`, {
    method: 'POST',
    credentials: 'include',
    headers: authorizedHeaders(authToken, { 'Content-Type': 'application/json' }),
    body: JSON.stringify({ message_id: messageId, message }),
  });
  if (!response.ok) throw await responseError(response);
}

export async function stopSession(
  sessionId: string,
  authToken: string | null,
  endpoint = getAiBaseUrl(),
): Promise<void> {
  const response = await fetch(`${endpoint}/sessions/${encodeURIComponent(sessionId)}/stop`, {
    method: 'POST',
    credentials: 'include',
    headers: authorizedHeaders(authToken),
  });
  if (!response.ok) throw await responseError(response);
}

export async function downloadOptimization(
  sessionId: string,
  jobId: string,
  authToken: string | null,
  endpoint = getAiBaseUrl(),
): Promise<Blob> {
  const response = await fetch(
    `${endpoint}/sessions/${encodeURIComponent(sessionId)}/optimizations/${encodeURIComponent(jobId)}/xlsx`,
    {
      method: 'GET',
      credentials: 'include',
      headers: authorizedHeaders(authToken),
    },
  );
  if (!response.ok) throw await responseError(response);
  return response.blob();
}

export async function scheduleRevision(scheduleYaml: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(scheduleYaml));
  return Array.from(new Uint8Array(digest))
    .map(byte => byte.toString(16).padStart(2, '0'))
    .join('');
}

export async function updateSessionSchedule(
  sessionId: string,
  scheduleYaml: string,
  authToken: string | null,
  endpoint = getAiBaseUrl(),
): Promise<void> {
  const response = await fetch(`${endpoint}/sessions/${encodeURIComponent(sessionId)}/schedule`, {
    method: 'PUT',
    credentials: 'include',
    headers: authorizedHeaders(authToken, { 'Content-Type': 'application/json' }),
    body: JSON.stringify({ schedule_yaml: scheduleYaml }),
  });
  if (!response.ok) throw await responseError(response);
}

export async function approveProposal(
  sessionId: string,
  scheduleYaml: string,
  authToken: string | null,
  endpoint = getAiBaseUrl(),
): Promise<string> {
  const response = await fetch(`${endpoint}/sessions/${encodeURIComponent(sessionId)}/proposal/approve`, {
    method: 'POST',
    credentials: 'include',
    headers: authorizedHeaders(authToken, { 'Content-Type': 'application/json' }),
    body: JSON.stringify({ base_sha256: await scheduleRevision(scheduleYaml) }),
  });
  if (!response.ok) throw await responseError(response);

  const body = await response.json() as { schedule_yaml?: unknown };
  if (typeof body.schedule_yaml !== 'string' || !body.schedule_yaml) {
    throw new Error('The AI backend returned an invalid proposal.');
  }
  return body.schedule_yaml;
}

export async function rejectProposal(
  sessionId: string,
  authToken: string | null,
  endpoint = getAiBaseUrl(),
): Promise<void> {
  const response = await fetch(`${endpoint}/sessions/${encodeURIComponent(sessionId)}/proposal/reject`, {
    method: 'POST',
    credentials: 'include',
    headers: authorizedHeaders(authToken),
  });
  if (!response.ok) throw await responseError(response);
}
