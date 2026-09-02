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

// This test is mostly AI generated.

import {
  approveProposal,
  createSession,
  getAiBaseUrl,
  getCapabilities,
  rejectProposal,
  scheduleRevision,
  streamMessage,
  updateSessionSchedule,
} from './aiClient';

function streamedResponse(chunks: string[]): Response {
  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    start(controller) {
      chunks.forEach(chunk => controller.enqueue(encoder.encode(chunk)));
      controller.close();
    },
  });
  return new Response(stream, { status: 200, headers: { 'Content-Type': 'text/event-stream' } });
}

describe('AI client', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('bypasses the buffering Next.js proxy during local development', () => {
    expect(getAiBaseUrl()).toBe('http://localhost:8001');
  });

  it('creates a browser-owned session', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ id: 'session-id' }),
      { status: 201, headers: { 'Content-Type': 'application/json' } },
    ));
    vi.stubGlobal('fetch', fetchMock);

    await expect(createSession('description: test')).resolves.toBe('session-id');
    expect(fetchMock).toHaveBeenCalledWith('http://localhost:8001/sessions', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ schedule_yaml: 'description: test' }),
    });
  });

  it('validates attachment capabilities', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      image_attachments: {
        enabled: true,
        accepted_media_types: ['image/png'],
        max_files: 2,
        max_bytes_per_file: 5000,
      },
      document_attachments: {
        enabled: true,
        accepted_extensions: ['.txt', '.md', '.csv', '.pdf', '.xlsx'],
        max_files: 3,
        max_bytes_per_file: 5000000,
      },
    }), { status: 200, headers: { 'Content-Type': 'application/json' } })));

    await expect(getCapabilities()).resolves.toEqual({
      image_attachments: {
        enabled: true,
        accepted_media_types: ['image/png'],
        max_files: 2,
        max_bytes_per_file: 5000,
      },
      document_attachments: {
        enabled: true,
        accepted_extensions: ['.txt', '.md', '.csv', '.pdf', '.xlsx'],
        max_files: 3,
        max_bytes_per_file: 5000000,
      },
    });
  });

  it('parses deltas split across network chunks', async () => {
    const fetchMock = vi.fn().mockResolvedValue(streamedResponse([
      'event: delta\ndata: {"text":"Hel',
      'lo"}\n\nevent: delta\ndata: {"text":" world"}\n\n',
      'event: done\ndata: {"message_id":"message-id"}\n\n',
    ]));
    vi.stubGlobal('fetch', fetchMock);
    const deltas: string[] = [];
    const onDone = vi.fn();
    const controller = new AbortController();

    await streamMessage(
      'session/id',
      'Who works?',
      { onDelta: delta => deltas.push(delta), onDone },
      controller.signal,
    );

    expect(deltas).toEqual(['Hello', ' world']);
    expect(onDone).toHaveBeenCalledOnce();
    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:8001/sessions/session%2Fid/messages',
      expect.objectContaining({
        body: JSON.stringify({ message: 'Who works?' }),
        credentials: 'include',
      }),
    );
  });

  it('delivers a streamed delta before the response completes', async () => {
    const encoder = new TextEncoder();
    let streamController: ReadableStreamDefaultController<Uint8Array> | undefined;
    const response = new Response(new ReadableStream({
      start(controller) {
        streamController = controller;
      },
    }), { status: 200, headers: { 'Content-Type': 'text/event-stream' } });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response));
    const deltas: string[] = [];
    const onDone = vi.fn();

    const streaming = streamMessage(
      'session-id',
      'Question',
      { onDelta: delta => deltas.push(delta), onDone },
      new AbortController().signal,
    );
    streamController?.enqueue(encoder.encode('event: delta\ndata: {"text":"First"}\n\n'));

    await vi.waitFor(() => expect(deltas).toEqual(['First']));
    expect(onDone).not.toHaveBeenCalled();

    streamController?.enqueue(encoder.encode('event: done\ndata: {"message_id":"message-id"}\n\n'));
    streamController?.close();
    await streaming;
    expect(onDone).toHaveBeenCalledOnce();
  });

  it('surfaces a provider status with its backend error ID', async () => {
    const providerError = 'The AI provider returned HTTP 525. Error ID: 72dc8f31-45af-410d-9fc2-41bdf1fc718f.';
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streamedResponse([
      `event: error\ndata: ${JSON.stringify({ message: providerError })}\n\n`,
    ])));

    await expect(streamMessage(
      'session-id',
      'Question',
      { onDelta: vi.fn() },
      new AbortController().signal,
    )).rejects.toThrow(providerError);
  });

  it('sends images as multipart form data', async () => {
    const fetchMock = vi.fn().mockResolvedValue(streamedResponse([
      'event: done\ndata: {"message_id":"message-id"}\n\n',
    ]));
    vi.stubGlobal('fetch', fetchMock);
    const image = new File(['image bytes'], 'ward.png', { type: 'image/png' });

    await streamMessage(
      'session-id',
      'What is shown?',
      { onDelta: vi.fn() },
      new AbortController().signal,
      { images: [image] },
    );

    const request = fetchMock.mock.calls[0][1] as RequestInit;
    expect(request.headers).toBeUndefined();
    expect(request.body).toBeInstanceOf(FormData);
    const form = request.body as FormData;
    expect(form.get('message')).toBe('What is shown?');
    expect(form.getAll('images')).toEqual([image]);
  });

  it('sends text documents as multipart form data', async () => {
    const fetchMock = vi.fn().mockResolvedValue(streamedResponse([
      'event: done\ndata: {"message_id":"message-id"}\n\n',
    ]));
    vi.stubGlobal('fetch', fetchMock);
    const document = new File(['name,shift\nAlice,day\n'], 'staff.csv', { type: 'text/csv' });

    await streamMessage(
      'session-id',
      'Check the file.',
      { onDelta: vi.fn() },
      new AbortController().signal,
      { documents: [document] },
    );

    const request = fetchMock.mock.calls[0][1] as RequestInit;
    expect(request.headers).toBeUndefined();
    expect(request.body).toBeInstanceOf(FormData);
    const form = request.body as FormData;
    expect(form.get('message')).toBe('Check the file.');
    expect(form.getAll('documents')).toEqual([document]);
  });

  it('forwards tool use and a proposal to the caller', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streamedResponse([
      'event: reasoning\ndata: {"text":"Checking people."}\n\n',
      'event: tool_start\ndata: {"name":"bash","arguments":"{\\"command\\":\\"sed -n 1p schedule.yaml\\"}"}\n\n',
      'event: tool\ndata: {"name":"bash","arguments":"{\\"command\\":\\"sed -n 1p schedule.yaml\\"}","result":"exit_code: 0","ok":true}\n\n',
      'event: schedule_change\ndata: {"schedule_yaml":"people:\\n  - id: Head\\n"}\n\n',
      'event: delta\ndata: {"text":"Renamed P1."}\n\n',
      'event: proposal\ndata: {"diff":"- people.items[0].id"}\n\n',
      'event: done\ndata: {"message_id":"1"}\n\n',
    ])));
    const toolStarts: string[] = [];
    const tools: string[] = [];
    const reasoning: string[] = [];
    const scheduleChanges: string[] = [];
    const diffs: string[] = [];
    const texts: string[] = [];

    await streamMessage(
      'session-id',
      'Rename P1.',
      {
        onDelta: text => texts.push(text),
        onReasoning: text => reasoning.push(text),
        onToolStart: activity => toolStarts.push(`${activity.name}:${activity.arguments}`),
        onTool: activity => tools.push(`${activity.name}:${activity.ok}:${activity.result}`),
        onScheduleChange: scheduleYaml => scheduleChanges.push(scheduleYaml),
        onProposal: diff => diffs.push(diff),
      },
      new AbortController().signal,
    );

    expect(toolStarts).toEqual(['bash:{"command":"sed -n 1p schedule.yaml"}']);
    expect(tools).toEqual(['bash:true:exit_code: 0']);
    expect(reasoning).toEqual(['Checking people.']);
    expect(scheduleChanges).toEqual(['people:\n  - id: Head\n']);
    expect(texts).toEqual(['Renamed P1.']);
    expect(diffs).toEqual(['- people.items[0].id']);
  });

  it('approves a proposal with the revision the browser holds', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ schedule_yaml: 'description: approved\n' }),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    ));
    vi.stubGlobal('fetch', fetchMock);

    await expect(approveProposal('session-id', 'description: test')).resolves.toBe('description: approved\n');
    expect(fetchMock).toHaveBeenCalledWith('http://localhost:8001/sessions/session-id/proposal/approve', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ base_sha256: await scheduleRevision('description: test') }),
    });
  });

  it('reports the backend reason when a proposal cannot be approved', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: 'The schedule changed after this proposal was created, so it was discarded.' }),
      { status: 409, headers: { 'Content-Type': 'application/json' } },
    )));

    await expect(approveProposal('session-id', 'description: test')).rejects.toThrow(
      'The schedule changed after this proposal was created, so it was discarded.',
    );
  });

  it('rejects a proposal and refreshes a session schedule', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal('fetch', fetchMock);

    await rejectProposal('session-id');
    await updateSessionSchedule('session-id', 'description: newer');

    expect(fetchMock.mock.calls[0][0]).toBe('http://localhost:8001/sessions/session-id/proposal/reject');
    expect(fetchMock.mock.calls[1][0]).toBe('http://localhost:8001/sessions/session-id/schedule');
    expect(fetchMock.mock.calls[1][1]).toMatchObject({
      method: 'PUT',
      body: JSON.stringify({ schedule_yaml: 'description: newer' }),
    });
  });

  it('treats a tool event without detail as a successful call', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streamedResponse([
      'event: tool\ndata: {"name":"bash"}\n\n',
      'event: done\ndata: {"message_id":"1"}\n\n',
    ])));
    const tools: { name: string; ok: boolean; result: string }[] = [];

    await streamMessage('session-id', 'Look.', { onDelta: () => {}, onTool: activity => tools.push(activity) },
      new AbortController().signal);

    expect(tools).toEqual([{ name: 'bash', arguments: '', result: '', ok: true }]);
  });

  it('rejects malformed schedule change events', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streamedResponse([
      'event: schedule_change\ndata: {"schedule_yaml":3}\n\n',
    ])));

    await expect(streamMessage(
      'session-id',
      'Look.',
      { onDelta: () => {} },
      new AbortController().signal,
    )).rejects.toThrow('The AI backend returned an invalid schedule change.');
  });
});
