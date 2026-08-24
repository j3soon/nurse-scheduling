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

export interface StreamCallbacks {
  onDelta: (text: string) => void;
  onDone?: () => void;
}

export interface AiCapabilities {
  image_attachments: {
    enabled: boolean;
    accepted_media_types: string[];
    max_files: number;
    max_bytes_per_file: number;
  };
}

interface SessionResponse {
  id: string;
}

interface SsePayload {
  text?: unknown;
  message?: unknown;
}

export function getAiBaseUrl(): string {
  const configuredUrl = process.env.NEXT_PUBLIC_AI_API_URL?.trim().replace(/\/$/, '');
  if (configuredUrl) return configuredUrl;
  if (process.env.NODE_ENV !== 'production' && typeof window !== 'undefined') {
    return `${window.location.protocol}//${window.location.hostname}:8001`;
  }
  return '/ai';
}

async function responseError(response: Response): Promise<Error> {
  try {
    const body = await response.json() as { detail?: unknown };
    if (typeof body.detail === 'string') return new Error(body.detail);
  } catch {
    // Fall back to a stable error when the response is not JSON.
  }
  return new Error(`The AI backend returned HTTP ${response.status}.`);
}

export async function getCapabilities(signal?: AbortSignal): Promise<AiCapabilities> {
  const response = await fetch(`${getAiBaseUrl()}/capabilities`, {
    credentials: 'include',
    signal,
  });
  if (!response.ok) throw await responseError(response);

  const body = await response.json() as Partial<AiCapabilities>;
  const images = body.image_attachments;
  if (
    typeof images?.enabled !== 'boolean'
    || !Array.isArray(images.accepted_media_types)
    || !images.accepted_media_types.every(mediaType => typeof mediaType === 'string')
    || !Number.isInteger(images.max_files)
    || images.max_files <= 0
    || !Number.isInteger(images.max_bytes_per_file)
    || images.max_bytes_per_file <= 0
  ) {
    throw new Error('The AI backend returned invalid capabilities.');
  }
  return body as AiCapabilities;
}

export async function createSession(scheduleYaml: string): Promise<string> {
  const response = await fetch(`${getAiBaseUrl()}/sessions`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
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
  images: File[] = [],
): Promise<void> {
  let body: BodyInit;
  let headers: HeadersInit | undefined;
  if (images.length > 0) {
    const form = new FormData();
    form.append('message', message);
    images.forEach(image => form.append('images', image, image.name));
    body = form;
  } else {
    headers = { 'Content-Type': 'application/json' };
    body = JSON.stringify({ message });
  }

  const response = await fetch(`${getAiBaseUrl()}/sessions/${encodeURIComponent(sessionId)}/messages`, {
    method: 'POST',
    credentials: 'include',
    headers,
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
