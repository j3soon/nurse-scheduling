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

import type { SessionEvent, SessionStreamOptions } from './sessionEvents';
import {
  buildAuthHeaders,
  parseAuthRequirement,
  type AuthRequirement,
} from '@/utils/backendAuth';
import type { OptimizationProgressPoint } from '@/components/OptimizationProgressChart';

export interface ToolActivity {
  toolCallId?: string;
  name: string;
  arguments: string;
  result: string;
  ok: boolean;
}

export type ToolStartActivity = Pick<ToolActivity, 'toolCallId' | 'name' | 'arguments'>;

export interface OptimizationActivity {
  jobId: string;
  state: string;
  terminal: boolean;
  downloadable: boolean;
  result?: { outcome?: string; score?: number; solverStatus?: string; terminationReason?: string };
  error?: { code?: string; message?: string };
  request?: { solver?: string; timeoutSeconds?: number };
  backend?: {
    url?: string;
    appVersion?: string;
    apiVersion?: string;
    serviceName?: string;
    deploymentId?: string;
    instanceId?: string;
    requestTimeoutSeconds?: number;
    claimedPerformance?: { score: number; appVersion: string; measuredAt: string };
  };
}

export interface OptimizationProgressActivity {
  jobId: string;
  point: OptimizationProgressPoint;
}

export interface ContextUsage {
  usedChars: number;
  maxChars: number;
  // Tokens of the latest provider request. The limit is optional when model metadata is unavailable.
  usedTokens?: number;
  maxTokens?: number;
}

export interface SessionReset {
  runIds: string[];
  activeRunId: string | null;
  terminalRunIds: string[];
  incomplete: boolean;
  proposalDiff: string | null;
}

export interface AiCapabilities {
  app_version?: string;
  auth: AuthRequirement | null;
  session_retention_seconds: number;
  file_attachments: {
    enabled: boolean;
    max_files: number;
    max_bytes_per_file: number;
    retained?: boolean;
  };
}

export interface UploadedFile {
  id: string;
  filename: string;
  media_type: string;
  bytes: number;
}

// The request messages added since the last assistant reply, in the order the model receives them.
export interface ModelInputMessage {
  kind: 'app' | 'question' | 'optimizer' | 'status';
  content: string;
  // Absolute history position of an app event, so a retried turn does not show it twice.
  index?: number;
  // Topic of an app event or status message, such as Proposal Rejected.
  title?: string;
}

export interface ModelInput {
  system: string;
  messages: ModelInputMessage[];
}

const MODEL_INPUT_KINDS = new Set(['app', 'question', 'optimizer', 'status']);

function isModelInputMessage(value: unknown): value is ModelInputMessage {
  if (typeof value !== 'object' || value === null) return false;
  const message = value as Partial<ModelInputMessage>;
  return typeof message.kind === 'string' && MODEL_INPUT_KINDS.has(message.kind)
    && typeof message.content === 'string'
    && (message.title === undefined || typeof message.title === 'string')
    && (message.kind === 'app' ? Number.isSafeInteger(message.index) : message.index === undefined);
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
  download_id?: unknown;
  arguments?: unknown;
  result?: unknown;
  ok?: unknown;
  schedule_yaml?: unknown;
  system?: unknown;
  messages?: unknown;
  used_tokens?: unknown;
  max_tokens?: unknown;
  message_id?: unknown;
  tool_call_id?: unknown;
  run_id?: unknown;
  trigger?: unknown;
  job_id?: unknown;
  state?: unknown;
  terminal?: unknown;
  downloadable?: unknown;
  error?: unknown;
  request?: unknown;
  backend?: unknown;
  progress?: unknown;
  used_chars?: unknown;
  max_chars?: unknown;
  dropped?: unknown;
  events?: unknown;
  incomplete?: unknown;
  active_run_id?: unknown;
  proposal_diff?: unknown;
}

// Older backends omit the ID, so callers fall back to matching by tool name.
function toolCallIdentity(payload: SsePayload): Pick<ToolActivity, 'toolCallId'> {
  return typeof payload.tool_call_id === 'string' && payload.tool_call_id
    ? { toolCallId: payload.tool_call_id }
    : {};
}

export class AiHttpError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = 'AiHttpError';
  }
}

export class AiStaleRunError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'AiStaleRunError';
  }
}

export function isAuthenticationError(error: unknown): boolean {
  return typeof error === 'object'
    && error !== null
    && 'status' in error
    && error.status === 401;
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
    || (files.retained !== undefined && typeof files.retained !== 'boolean')
  ) {
    throw new Error('The AI backend returned invalid capabilities.');
  }
  return {
    ...body,
    app_version: typeof body.app_version === 'string' && body.app_version.trim() ? body.app_version : undefined,
    auth,
    session_retention_seconds: sessionRetention,
  } as AiCapabilities;
}

export async function getBackendVersion(signal?: AbortSignal, endpoint = getAiBaseUrl()): Promise<string | undefined> {
  // Shared deployments mount AI at /ai and expose optimizer identity at its parent.
  const baseUrl = endpoint.replace(/\/+$/, '');
  if (!baseUrl.endsWith('/ai')) return undefined;
  try {
    const response = await fetch(`${baseUrl.slice(0, -3)}/info`, {
      credentials: 'omit',
      signal: AbortSignal.any([...(signal ? [signal] : []), AbortSignal.timeout(5000)]),
    });
    if (!response.ok) return undefined;
    const body = await response.json() as { app_version?: unknown };
    return typeof body?.app_version === 'string' && body.app_version.trim() ? body.app_version.trim() : undefined;
  } catch {
    return undefined;
  }
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

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function record(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null ? value as Record<string, unknown> : {};
}

function textField(value: unknown): string | undefined {
  return typeof value === 'string' ? value : undefined;
}

function numberField(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined;
}

function optimizationDetails(payload: SsePayload): Partial<OptimizationActivity> {
  const result = record(payload.result);
  const error = record(payload.error);
  const request = record(payload.request);
  const backend = record(payload.backend);
  const claimed = record(backend.claimed_performance);
  const score = numberField(claimed.score);
  return {
    ...(payload.result ? { result: {
      outcome: textField(result.outcome),
      score: numberField(result.score),
      solverStatus: textField(result.solver_status),
      terminationReason: textField(result.termination_reason),
    } } : {}),
    ...(payload.error ? { error: { code: textField(error.code), message: textField(error.message) } } : {}),
    ...(payload.request ? { request: {
      solver: textField(request.solver), timeoutSeconds: numberField(request.timeout_seconds),
    } } : {}),
    ...(payload.backend ? { backend: {
      url: textField(backend.url),
      appVersion: textField(backend.app_version),
      apiVersion: textField(backend.api_version),
      serviceName: textField(backend.service_name),
      deploymentId: textField(backend.deployment_id),
      instanceId: textField(backend.instance_id),
      requestTimeoutSeconds: numberField(backend.request_timeout_seconds),
      ...(score !== undefined && score > 0 && typeof claimed.app_version === 'string'
        && typeof claimed.measured_at === 'string' && Number.isFinite(Date.parse(claimed.measured_at))
        ? { claimedPerformance: { score, appVersion: claimed.app_version, measuredAt: claimed.measured_at } } : {}),
    } } : {}),
  };
}

function consumeEvent(block: string, callbacks: SessionStreamOptions): void {
  const lines = block.split('\n');
  const eventId = Number(lines.find(line => line.startsWith('id:'))?.slice('id:'.length).trim());
  const eventType = lines.find(line => line.startsWith('event:'))?.slice('event:'.length).trim() ?? 'message';
  const rawData = lines
    .filter(line => line.startsWith('data:'))
    .map(line => line.slice('data:'.length).trimStart())
    .join('\n');
  if (!rawData) return;
  if (eventType !== 'session_reset' && Number.isSafeInteger(eventId) && eventId > 0
    && eventId <= (callbacks.lastEventId ?? 0)) return;

  let payload: SsePayload;
  try {
    const parsed: unknown = JSON.parse(rawData);
    if (!isRecord(parsed)) throw new Error();
    payload = parsed;
  } catch {
    throw new Error('The AI backend returned an invalid stream.');
  }

  let events: SessionEvent[];
  if (eventType === 'session_reset') {
    if (!Array.isArray(payload.events)) throw new Error('The AI backend returned an invalid recovery snapshot.');
    const recovery = payload.events.map((entry: unknown) => {
      if (!isRecord(entry) || typeof entry.type !== 'string' || !isRecord(entry.data)) {
        throw new Error('The AI backend returned an invalid recovery snapshot.');
      }
      return { type: entry.type, data: entry.data };
    });
    const recoveredEvents = recovery.flatMap(event => decodeEvent(event.type, event.data));
    const runIds = [...new Set(recovery.flatMap(event =>
      typeof event.data.run_id === 'string' ? [event.data.run_id] : []))];
    const reset = {
      runIds,
      terminalRunIds: recovery.flatMap(event =>
        ['done', 'stopped', 'stale', 'error'].includes(event.type) && typeof event.data.run_id === 'string'
          ? [event.data.run_id] : []),
      activeRunId: typeof payload.active_run_id === 'string' ? payload.active_run_id : null,
      incomplete: payload.incomplete === true,
      proposalDiff: typeof payload.proposal_diff === 'string' && payload.proposal_diff ? payload.proposal_diff : null,
    };
    events = [
      { type: 'session_reset', reset },
      ...recoveredEvents,
      // Proposal ownership may have changed since the retained run produced it.
      { type: 'proposal', diff: reset.proposalDiff ?? '' },
    ];
  } else {
    events = decodeEvent(eventType, payload);
  }

  // Validate the whole frame before acknowledging or applying it. Acknowledge
  // before handlers so a failing handler cannot repeat an event on every reconnect.
  if (Number.isSafeInteger(eventId) && eventId >= 0) {
    callbacks.lastEventId = eventId;
    callbacks.onEventId?.(eventId);
  }
  for (const event of events) callbacks.onEvent(event);
}

function decodeEvent(eventType: string, payload: SsePayload): SessionEvent[] {
  const events: SessionEvent[] = [];
  const runId = typeof payload.run_id === 'string' ? payload.run_id : undefined;
  const emit = (event: SessionEvent) => events.push(runId === undefined ? event : { ...event, runId });
  if (runId) emit({ type: 'run_context', runId });

  if (eventType === 'run_start' && typeof payload.run_id === 'string') {
    emit({
      type: 'run_start', runId: payload.run_id,
      trigger: typeof payload.trigger === 'string' ? payload.trigger : 'background work',
    });
  } else if (eventType === 'delta' && typeof payload.text === 'string') {
    emit({ type: 'delta', text: payload.text });
  } else if (eventType === 'reasoning' && typeof payload.text === 'string') {
    emit({ type: 'reasoning', text: payload.text });
  } else if (eventType === 'truncated') {
    emit({ type: 'truncated' });
  } else if (eventType === 'tool_start' && typeof payload.name === 'string') {
    emit({
      type: 'tool_start',
      activity: {
        ...toolCallIdentity(payload),
        name: payload.name,
        arguments: typeof payload.arguments === 'string' ? payload.arguments : '',
      },
    });
  } else if (eventType === 'tool' && typeof payload.name === 'string') {
    emit({
      type: 'tool',
      activity: {
        ...toolCallIdentity(payload),
        name: payload.name,
        arguments: typeof payload.arguments === 'string' ? payload.arguments : '',
        result: typeof payload.result === 'string' ? payload.result : '',
        ok: payload.ok !== false,
      },
    });
  } else if (
    eventType === 'steering'
    && typeof payload.message_id === 'string'
    && typeof payload.message === 'string'
  ) {
    emit({ type: 'steering', messageId: payload.message_id, message: payload.message });
  } else if (eventType === 'schedule_change') {
    if (typeof payload.schedule_yaml !== 'string') {
      throw new Error('The AI backend returned an invalid schedule change.');
    }
    emit({ type: 'schedule_change', scheduleYaml: payload.schedule_yaml });
  } else if (eventType === 'download' && typeof payload.download_id === 'string') {
    emit({ type: 'download', downloadId: payload.download_id });
  } else if (eventType === 'proposal' && typeof payload.diff === 'string') {
    emit({ type: 'proposal', diff: payload.diff });
  } else if (
    eventType === 'optimization'
    && typeof payload.job_id === 'string'
    && typeof payload.state === 'string'
    && typeof payload.terminal === 'boolean'
    && typeof payload.downloadable === 'boolean'
  ) {
    emit({
      type: 'optimization',
      activity: {
        jobId: payload.job_id,
        state: payload.state,
        terminal: payload.terminal,
        downloadable: payload.downloadable,
        ...optimizationDetails(payload),
      },
    });
  } else if (eventType === 'optimization_progress' && typeof payload.job_id === 'string') {
    const point = payload.progress as Record<string, unknown> | null | undefined;
    if (
      typeof point === 'object' && point !== null
      && typeof point.currentBestScore === 'number' && Number.isFinite(point.currentBestScore)
      && typeof point.elapsedSeconds === 'number' && Number.isFinite(point.elapsedSeconds)
      && point.elapsedSeconds >= 0
    ) {
      emit({
        type: 'optimization_progress',
        activity: {
          jobId: payload.job_id,
          point: {
            currentBestScore: point.currentBestScore,
            elapsedSeconds: point.elapsedSeconds,
            commentCount: typeof point.commentCount === 'number' ? point.commentCount : null,
            solutionIndex: typeof point.solutionIndex === 'number' ? point.solutionIndex : null,
            source: typeof point.source === 'string' ? point.source : undefined,
          },
        },
      });
    }
  } else if (eventType === 'model_input') {
    if (typeof payload.system !== 'string' || !Array.isArray(payload.messages)
      || !payload.messages.every(isModelInputMessage)) {
      throw new Error('The AI backend returned an invalid model input.');
    }
    emit({ type: 'model_input', input: { system: payload.system, messages: payload.messages } });
  } else if (eventType === 'done') {
    emit({ type: 'done' });
  } else if (eventType === 'stopped') {
    emit({ type: 'stopped' });
  } else if (eventType === 'stale') {
    const message = typeof payload.message === 'string' ? payload.message : 'The AI response became stale.';
    emit({ type: 'stale', message });
  } else if (eventType === 'context_usage') {
    if (Number.isSafeInteger(payload.used_chars) && (payload.used_chars as number) >= 0
      && Number.isSafeInteger(payload.max_chars) && (payload.max_chars as number) > 0
      && (payload.used_chars as number) <= (payload.max_chars as number)) {
      const tokens: Pick<ContextUsage, 'usedTokens' | 'maxTokens'> = {};
      if (Number.isSafeInteger(payload.used_tokens) && (payload.used_tokens as number) >= 0) {
        tokens.usedTokens = payload.used_tokens as number;
        if (Number.isSafeInteger(payload.max_tokens) && (payload.max_tokens as number) > 0) {
          tokens.maxTokens = payload.max_tokens as number;
        }
      }
      emit({
        type: 'context_usage',
        usage: { usedChars: payload.used_chars as number, maxChars: payload.max_chars as number, ...tokens },
      });
    }
  } else if (eventType === 'history_trimmed') {
    const dropped = payload.dropped;
    if (typeof dropped === 'number' && Number.isInteger(dropped) && dropped > 0) {
      emit({ type: 'history_trimmed', dropped });
    }
  } else if (eventType === 'warning' && typeof payload.message === 'string') {
    emit({ type: 'warning', message: payload.message });
  } else if (eventType === 'error') {
    const message = typeof payload.message === 'string' ? payload.message : 'The AI response failed.';
    emit({ type: 'error', message });
  }
  return events;
}

async function postMessage(
  sessionId: string,
  message: string,
  signal: AbortSignal,
  authToken: string | null,
  endpoint: string,
  accept: string,
): Promise<Response> {
  const response = await fetch(`${endpoint}/sessions/${encodeURIComponent(sessionId)}/messages`, {
    method: 'POST',
    credentials: 'include',
    headers: authorizedHeaders(authToken, { Accept: accept, 'Content-Type': 'application/json' }),
    body: JSON.stringify({ message }),
    signal,
  });
  if (!response.ok) throw await responseError(response);
  return response;
}

/** Post a question. Upload its files first with `uploadFiles`, so the backend records them as their own event. */
export async function sendMessage(
  sessionId: string,
  message: string,
  signal: AbortSignal,
  authToken: string | null,
  endpoint = getAiBaseUrl(),
): Promise<string> {
  const response = await postMessage(sessionId, message, signal, authToken, endpoint, 'application/json');
  const body = await response.json() as { run_id?: unknown };
  if (typeof body.run_id !== 'string' || !body.run_id) throw new Error('The AI backend returned an invalid run ID.');
  return body.run_id;
}

/** Compatibility consumer. The browser uses sendMessage and the session GET stream. */
export async function streamMessage(
  sessionId: string,
  message: string,
  callbacks: SessionStreamOptions,
  signal: AbortSignal,
  authToken: string | null,
  endpoint = getAiBaseUrl(),
): Promise<void> {
  const response = await postMessage(sessionId, message, signal, authToken, endpoint, 'text/event-stream');
  await consumeStream(response, callbacks);
}

async function consumeStream(response: Response, callbacks: SessionStreamOptions, replayable = false): Promise<void> {
  if (!response.body) throw new Error('The AI backend returned an empty stream.');

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  const streamCallbacks = { ...callbacks };
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      buffer = (buffer + decoder.decode(value, { stream: !done })).replace(/\r\n/g, '\n');

      let boundary = buffer.indexOf('\n\n');
      while (boundary >= 0) {
        consumeEvent(buffer.slice(0, boundary), streamCallbacks);
        buffer = buffer.slice(boundary + 2);
        boundary = buffer.indexOf('\n\n');
      }

      if (done) break;
    }
    // A replay cursor only advances over complete frames. The next connection
    // must replay an event whose delimiter was lost in transit.
    if (!replayable && buffer.trim()) consumeEvent(buffer, streamCallbacks);
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}

export async function streamSessionEvents(
  sessionId: string,
  callbacks: SessionStreamOptions,
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
  await consumeStream(response, callbacks, true);
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

export async function getUploads(sessionId: string, authToken: string | null, endpoint = getAiBaseUrl(), signal?: AbortSignal): Promise<UploadedFile[]> {
  const response = await fetch(`${endpoint}/sessions/${encodeURIComponent(sessionId)}/uploads`, {
    credentials: 'include', headers: authorizedHeaders(authToken), signal,
  });
  if (!response.ok) throw await responseError(response);
  return parseUploadList(await response.json());
}

export async function uploadFiles(
  sessionId: string,
  files: File[],
  authToken: string | null,
  endpoint = getAiBaseUrl(),
  signal?: AbortSignal,
): Promise<UploadedFile[]> {
  const form = new FormData();
  files.forEach(file => form.append('files', file, file.name));
  const response = await fetch(`${endpoint}/sessions/${encodeURIComponent(sessionId)}/uploads`, {
    method: 'POST', credentials: 'include', headers: authorizedHeaders(authToken), body: form, signal,
  });
  if (!response.ok) throw await responseError(response);
  return parseUploadList(await response.json());
}

function parseUploadList(files: unknown): UploadedFile[] {
  if (!Array.isArray(files) || files.some(file => typeof file.id !== 'string' || typeof file.filename !== 'string' || typeof file.media_type !== 'string' || !Number.isSafeInteger(file.bytes) || file.bytes < 0)) {
    throw new Error('The AI backend returned an invalid upload list.');
  }
  return files;
}

export async function removeUpload(sessionId: string, uploadId: string, authToken: string | null, endpoint = getAiBaseUrl()): Promise<void> {
  const response = await fetch(`${endpoint}/sessions/${encodeURIComponent(sessionId)}/uploads/${encodeURIComponent(uploadId)}`, {
    method: 'DELETE', credentials: 'include', headers: authorizedHeaders(authToken),
  });
  if (!response.ok) throw await responseError(response);
}

export async function downloadGeneratedZip(
  sessionId: string,
  downloadId: string,
  authToken: string | null,
  endpoint = getAiBaseUrl(),
): Promise<Blob> {
  const response = await fetch(
    `${endpoint}/sessions/${encodeURIComponent(sessionId)}/downloads/${encodeURIComponent(downloadId)}`,
    { credentials: 'include', headers: authorizedHeaders(authToken) },
  );
  if (!response.ok) throw await responseError(response);
  return response.blob();
}

export async function removeGeneratedZip(sessionId: string, downloadId: string, authToken: string | null, endpoint = getAiBaseUrl()): Promise<void> {
  const response = await fetch(`${endpoint}/sessions/${encodeURIComponent(sessionId)}/downloads/${encodeURIComponent(downloadId)}`, {
    method: 'DELETE', credentials: 'include', headers: authorizedHeaders(authToken),
  });
  if (!response.ok) throw await responseError(response);
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
