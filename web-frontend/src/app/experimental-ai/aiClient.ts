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

export interface ToolActivity {
  name: string;
  arguments: string;
  result: string;
  ok: boolean;
}

export type ToolStartActivity = Pick<ToolActivity, 'name' | 'arguments'>;

export interface StreamCallbacks {
  onDelta: (text: string) => void;
  onReasoning?: (text: string) => void;
  onToolStart?: (activity: ToolStartActivity) => void;
  onTool?: (activity: ToolActivity) => void;
  onScheduleChange?: (scheduleYaml: string) => void;
  onProposal?: (diff: string) => void;
  onDone?: () => void;
}

export interface AiCapabilities {
  auth: AuthRequirement | null;
  image_attachments: {
    enabled: boolean;
    accepted_media_types: string[];
    max_files: number;
    max_bytes_per_file: number;
  };
  document_attachments: {
    enabled: boolean;
    accepted_extensions: string[];
    max_files: number;
    max_bytes_per_file: number;
  };
}

export interface MessageAttachments {
  images?: File[];
  documents?: File[];
}

interface SessionResponse {
  id: string;
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
}

export class AiHttpError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = 'AiHttpError';
  }
}

export const PRODUCTION_AI_API_URL = 'https://api.nursescheduling.org/ai';
export const LOCAL_AI_API_URL = 'http://localhost:8001';

export function getAiBaseUrl(): string {
  const configuredUrl = process.env.NEXT_PUBLIC_AI_API_URL?.trim().replace(/\/$/, '');
  if (configuredUrl) return configuredUrl;
  return PRODUCTION_AI_API_URL;
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
  const images = body.image_attachments;
  const documents = body.document_attachments;
  if (
    typeof images?.enabled !== 'boolean'
    || !Array.isArray(images.accepted_media_types)
    || !images.accepted_media_types.every(mediaType => typeof mediaType === 'string')
    || !Number.isInteger(images.max_files)
    || images.max_files <= 0
    || !Number.isInteger(images.max_bytes_per_file)
    || images.max_bytes_per_file <= 0
    || typeof documents?.enabled !== 'boolean'
    || !Array.isArray(documents.accepted_extensions)
    || !documents.accepted_extensions.every(extension => typeof extension === 'string')
    || !Number.isInteger(documents.max_files)
    || documents.max_files <= 0
    || !Number.isInteger(documents.max_bytes_per_file)
    || documents.max_bytes_per_file <= 0
  ) {
    throw new Error('The AI backend returned invalid capabilities.');
  }
  return { ...body, auth } as AiCapabilities;
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

function consumeEvent(block: string, callbacks: StreamCallbacks): void {
  const lines = block.split('\n');
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

  if (eventType === 'delta' && typeof payload.text === 'string') {
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
  } else if (eventType === 'schedule_change') {
    if (typeof payload.schedule_yaml !== 'string') {
      throw new Error('The AI backend returned an invalid schedule change.');
    }
    callbacks.onScheduleChange?.(payload.schedule_yaml);
  } else if (eventType === 'proposal' && typeof payload.diff === 'string') {
    callbacks.onProposal?.(payload.diff);
  } else if (eventType === 'done') {
    callbacks.onDone?.();
  } else if (eventType === 'error') {
    throw new Error(typeof payload.message === 'string' ? payload.message : 'The AI response failed.');
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
  const images = attachments.images ?? [];
  const documents = attachments.documents ?? [];
  let body: BodyInit;
  let headers: Record<string, string> | undefined;
  if (images.length > 0 || documents.length > 0) {
    const form = new FormData();
    form.append('message', message);
    images.forEach(image => form.append('images', image, image.name));
    documents.forEach(document => form.append('documents', document, document.name));
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
