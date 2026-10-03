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
  AiStaleRunError,
  PRODUCTION_AI_API_URL,
  approveProposal,
  createSession,
  downloadOptimization,
  getAiBaseUrl,
  getCapabilities,
  getBackendVersion,
  getSessionStatus,
  isOfficialAiEndpoint,
  queueMessage,
  rejectProposal,
  scheduleRevision,
  streamMessage,
  sendMessage,
  streamSessionEvents,
  stopSession,
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

  it('uses the hosted AI backend by default', () => {
    expect(getAiBaseUrl()).toBe('https://api.nursescheduling.org/ai');
  });

  it('creates a browser-owned session', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ id: 'session-id' }),
      { status: 201, headers: { 'Content-Type': 'application/json' } },
    ));
    vi.stubGlobal('fetch', fetchMock);

    await expect(createSession('description: test', 'ai-client-token')).resolves.toBe('session-id');
    expect(fetchMock).toHaveBeenCalledWith('https://api.nursescheduling.org/ai/sessions', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ai-client-token' },
      body: JSON.stringify({ schedule_yaml: 'description: test' }),
    });
  });

  it('validates attachment capabilities', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      file_attachments: {
        enabled: true,
        max_files: 5,
        max_bytes_per_file: 5000000,
      },
    }), { status: 200, headers: { 'Content-Type': 'application/json' } })));

    await expect(getCapabilities()).resolves.toEqual({
      auth: null,
      session_retention_seconds: 172800,
      file_attachments: {
        enabled: true,
        max_files: 5,
        max_bytes_per_file: 5000000,
      },
    });
  });

  it.each([
    ['https://api.nursescheduling.org/ai', 'https://api.nursescheduling.org/info'],
    ['https://api.example.test/prefix/ai/', 'https://api.example.test/prefix/info'],
    ['/ai', '/info'],
  ])('reads the shared backend version for %s', async (endpoint, infoUrl) => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ app_version: 'v0.2.0-production' })));
    vi.stubGlobal('fetch', fetchMock);
    await expect(getBackendVersion(undefined, endpoint)).resolves.toBe('v0.2.0-production');
    expect(fetchMock).toHaveBeenCalledWith(infoUrl, { credentials: 'omit', signal: expect.any(AbortSignal) });
  });

  it.each([new Response('offline', { status: 503 }), new Response('{}'), new Response('invalid JSON')])(
    'tolerates unavailable optimizer identity', async response => {
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response));
      await expect(getBackendVersion(undefined, '/ai')).resolves.toBeUndefined();
    },
  );

  it('keeps standalone AI endpoints independent of an assumed optimizer address', async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    await expect(getBackendVersion(undefined, 'http://localhost:8001')).resolves.toBeUndefined();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('checks a stored session without sending a keepalive request', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ expires_in_seconds: 120 }),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    ));
    vi.stubGlobal('fetch', fetchMock);

    await expect(getSessionStatus('session/id', 'ai-client-token')).resolves.toBe(120);
    expect(fetchMock).toHaveBeenCalledWith(
      'https://api.nursescheduling.org/ai/sessions/session%2Fid',
      {
        credentials: 'include',
        headers: { Authorization: 'Bearer ai-client-token' },
      },
    );
  });

  it('reads the advertised AI authentication requirement', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      auth: { required: true, scheme: 'Bearer' },
      file_attachments: {
        enabled: true,
        max_files: 1,
        max_bytes_per_file: 1,
      },
    }), { status: 200, headers: { 'Content-Type': 'application/json' } })));

    await expect(getCapabilities()).resolves.toMatchObject({
      auth: { required: true, scheme: 'bearer' },
    });
  });

  it('preserves an authentication failure status for the credential UI', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: 'Backend credentials are invalid.' }),
      { status: 401, headers: { 'Content-Type': 'application/json' } },
    )));

    await expect(createSession('description: test', 'stale-token')).rejects.toMatchObject({
      message: 'Backend credentials are invalid.',
      status: 401,
    });
  });

  it('submits a message and returns its admitted run ID without reading SSE', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ run_id: 'r' }), { status: 202 }));
    vi.stubGlobal('fetch', fetchMock);
    expect(await sendMessage('s', 'Hello', new AbortController().signal, 'token')).toBe('r');
    expect(fetchMock).toHaveBeenCalledWith(expect.stringMatching('/s/messages'), expect.objectContaining({
      headers: { Accept: 'application/json', 'Content-Type': 'application/json', Authorization: 'Bearer token' },
    }));
  });

  it('recovers a run once through session_reset and continues with the next event', async () => {
    const recovery = {
      events: [
        { type: 'run_start', data: { run_id: 'r', trigger: 'user' } },
        { type: 'delta', data: { run_id: 'r', text: 'Recovered answer.' } },
        { type: 'tool', data: { run_id: 'r', tool_call_id: 't', name: 'read', result: 'Read', ok: true } },
      ],
      active_run_id: 'r', incomplete: true, proposal_diff: '',
    };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streamedResponse([
      `id: 8\nevent: session_reset\ndata: ${JSON.stringify(recovery)}\n\n`,
      'id: 9\nevent: done\ndata: {"run_id":"r"}\n\n',
      'id: 9\nevent: done\ndata: {"run_id":"r"}\n\n',
    ])));
    const reset = vi.fn();
    const delta = vi.fn();
    const done = vi.fn();
    const cursor = vi.fn();
    const tool = vi.fn();
    const proposal = vi.fn();
    const foreground = { onDelta: delta, onDone: done, onTool: tool, onReset: vi.fn() };
    await streamSessionEvents('s', {
      lastEventId: 5, onDelta: vi.fn(), forRun: id => id === 'r' ? foreground : undefined,
      onReset: reset, onEventId: cursor, onProposal: proposal,
    }, new AbortController().signal, null);
    expect(reset).toHaveBeenCalledWith(expect.objectContaining({ runIds: ['r'], activeRunId: 'r', incomplete: true }));
    expect(foreground.onReset).toHaveBeenCalledOnce();
    expect(delta).toHaveBeenCalledExactlyOnceWith('Recovered answer.');
    expect(tool).toHaveBeenCalledWith(expect.objectContaining({ toolCallId: 't' }));
    expect(done).toHaveBeenCalledExactlyOnceWith('r');
    expect(cursor.mock.calls.map(([id]) => id)).toEqual([8, 9]);
    expect(proposal).toHaveBeenCalledExactlyOnceWith('');
  });

  it('parses deltas split across network chunks', async () => {
    const fetchMock = vi.fn().mockResolvedValue(streamedResponse([
      'event: delta\ndata: {"text":"Hel',
      'lo"}\n\nevent: delta\ndata: {"text":" world"}\n\n',
      'event: done\ndata: {"run_id":"message-id"}\n\n',
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
      'stream-token',
    );

    expect(deltas).toEqual(['Hello', ' world']);
    expect(onDone).toHaveBeenCalledOnce();
    expect(onDone).toHaveBeenCalledWith('message-id');
    expect(fetchMock).toHaveBeenCalledWith(
      'https://api.nursescheduling.org/ai/sessions/session%2Fid/messages',
      expect.objectContaining({
        body: JSON.stringify({ message: 'Who works?' }),
        credentials: 'include',
        headers: { Accept: 'text/event-stream', 'Content-Type': 'application/json', Authorization: 'Bearer stream-token' },
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
      null,
    );
    streamController?.enqueue(encoder.encode('event: delta\ndata: {"text":"First"}\n\n'));

    await vi.waitFor(() => expect(deltas).toEqual(['First']));
    expect(onDone).not.toHaveBeenCalled();

    streamController?.enqueue(encoder.encode('event: done\ndata: {"run_id":"message-id"}\n\n'));
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
      null,
    )).rejects.toThrow(providerError);
  });

  it('reports when streamed output was discarded as stale', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streamedResponse([
      'event: delta\ndata: {"text":"Obsolete"}\n\n',
      'event: stale\ndata: {"message":"The schedule changed."}\n\n',
    ])));

    await expect(streamMessage(
      'session-id',
      'Question',
      { onDelta: vi.fn() },
      new AbortController().signal,
      null,
    )).rejects.toEqual(new AiStaleRunError('The schedule changed.'));
  });

  it('sends arbitrary files as multipart form data', async () => {
    const fetchMock = vi.fn().mockResolvedValue(streamedResponse([
      'event: done\ndata: {"run_id":"message-id"}\n\n',
    ]));
    vi.stubGlobal('fetch', fetchMock);
    const image = new File(['image bytes'], 'ward.png', { type: 'image/png' });

    await streamMessage(
      'session-id',
      'What is shown?',
      { onDelta: vi.fn() },
      new AbortController().signal,
      null,
      { files: [image] },
    );

    const request = fetchMock.mock.calls[0][1] as RequestInit;
    expect(request.headers).toEqual({ Accept: 'text/event-stream' });
    expect(request.body).toBeInstanceOf(FormData);
    const form = request.body as FormData;
    expect(form.get('message')).toBe('What is shown?');
    expect(form.getAll('files')).toEqual([image]);
  });

  it('forwards tool use and a proposal to the caller', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streamedResponse([
      'event: reasoning\ndata: {"text":"Checking people."}\n\n',
      'event: tool_start\ndata: {"tool_call_id":"call-1","name":"bash","arguments":"{\\"command\\":\\"sed -n 1p schedule.yaml\\"}"}\n\n',
      'event: tool\ndata: {"tool_call_id":"call-1","name":"bash","arguments":"{\\"command\\":\\"sed -n 1p schedule.yaml\\"}","result":"exit_code: 0","ok":true}\n\n',
      'event: steering\ndata: {"message_id":"queued-1","message":"Focus on P2."}\n\n',
      'event: schedule_change\ndata: {"schedule_yaml":"people:\\n  - id: Head\\n"}\n\n',
      'event: delta\ndata: {"text":"Renamed P1."}\n\n',
      'event: truncated\ndata: {}\n\n',
      'event: proposal\ndata: {"diff":"- people.items[0].id"}\n\n',
      'event: done\ndata: {"run_id":"1"}\n\n',
    ])));
    const toolStarts: string[] = [];
    const tools: string[] = [];
    const reasoning: string[] = [];
    const scheduleChanges: string[] = [];
    const steering: string[] = [];
    const diffs: string[] = [];
    const texts: string[] = [];
    let truncated = 0;

    await streamMessage(
      'session-id',
      'Rename P1.',
      {
        onDelta: text => texts.push(text),
        onReasoning: text => reasoning.push(text),
        onTruncated: () => { truncated += 1; },
        onToolStart: activity => toolStarts.push(`${activity.toolCallId}:${activity.name}:${activity.arguments}`),
        onTool: activity => tools.push(`${activity.toolCallId}:${activity.name}:${activity.ok}:${activity.result}`),
        onSteering: (messageId, message) => steering.push(`${messageId}:${message}`),
        onScheduleChange: scheduleYaml => scheduleChanges.push(scheduleYaml),
        onProposal: diff => diffs.push(diff),
      },
      new AbortController().signal,
      null,
    );

    expect(toolStarts).toEqual(['call-1:bash:{"command":"sed -n 1p schedule.yaml"}']);
    expect(tools).toEqual(['call-1:bash:true:exit_code: 0']);
    expect(steering).toEqual(['queued-1:Focus on P2.']);
    expect(reasoning).toEqual(['Checking people.']);
    expect(scheduleChanges).toEqual(['people:\n  - id: Head\n']);
    expect(texts).toEqual(['Renamed P1.']);
    expect(truncated).toBe(1);
    expect(diffs).toEqual(['- people.items[0].id']);
  });

  it('keeps run lifecycle identity separate from queued user message identity', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streamedResponse([
      'id: 1\nevent: run_start\ndata: {"run_id":"run-1","trigger":"optimizer"}\n\n',
      'id: 2\nevent: steering\ndata: {"run_id":"run-1","message_id":"queued-1","message":"Focus on P2."}\n\n',
      'id: 3\nevent: stopped\ndata: {"run_id":"run-1"}\n\n',
    ])));
    const start = vi.fn();
    const context = vi.fn();
    const steering = vi.fn();
    const stopped = vi.fn();

    await streamSessionEvents(
      'session/id',
      { onDelta: () => {}, onRunStart: start, onRunContext: context, onSteering: steering, onStopped: stopped },
      new AbortController().signal,
      null,
    );

    expect(start).toHaveBeenCalledWith('run-1', 'optimizer');
    expect(context.mock.calls).toEqual([['run-1'], ['run-1'], ['run-1']]);
    expect(steering).toHaveBeenCalledWith('queued-1', 'Focus on P2.');
    expect(stopped).toHaveBeenCalledWith('run-1');
  });

  it('receives context usage and ignores invalid budgets', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streamedResponse([
      'event: context_usage\ndata: {"used_chars":250,"max_chars":1000}\n\n',
      'event: context_usage\ndata: {"used_chars":10,"max_chars":0}\n\n',
      'event: context_usage\ndata: {"used_chars":-1,"max_chars":100}\n\n',
      'event: context_usage\ndata: {"used_chars":101,"max_chars":100}\n\n',
      'event: context_usage\ndata: {"used_chars":"25","max_chars":100}\n\n',
    ])));
    const onContextUsage = vi.fn();
    await streamSessionEvents('session', { onDelta: vi.fn(), onContextUsage }, new AbortController().signal, null);
    expect(onContextUsage).toHaveBeenCalledExactlyOnceWith({ usedChars: 250, maxChars: 1000 });
  });

  it('reports a trimmed prompt history and ignores a meaningless count', async () => {
    const fetchMock = vi.fn().mockResolvedValue(streamedResponse([
      'id: 1\nevent: history_trimmed\ndata: {"dropped":0}\n\n',
      'id: 2\nevent: history_trimmed\ndata: {"dropped":"many"}\n\n',
      'id: 3\nevent: history_trimmed\ndata: {"dropped":6}\n\n',
      'id: 4\nevent: done\ndata: {"run_id":"background-1"}\n\n',
    ]));
    vi.stubGlobal('fetch', fetchMock);
    const trimmed = vi.fn();

    await streamSessionEvents(
      'session/id',
      { onDelta: () => {}, onHistoryTrimmed: trimmed },
      new AbortController().signal,
      null,
    );

    expect(trimmed).toHaveBeenCalledTimes(1);
    expect(trimmed).toHaveBeenCalledWith(6);
  });

  it('decodes optimizer provenance and preserves a zero final score', async () => {
    const payload = {
      job_id: 'opt-1', state: 'completed', terminal: true, downloadable: true,
      result: { outcome: 'optimal', score: 0, solver_status: 'OPTIMAL', termination_reason: 'completed' },
      request: { solver: 'ortools/cp-sat', timeout_seconds: 300 },
      backend: { url: 'http://optimizer:8000', app_version: 'v0.4.3', request_timeout_seconds: 30,
        claimed_performance: { score: 125, app_version: 'v0.4.2', measured_at: '2026-09-18T01:00:00Z' } },
    };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streamedResponse([
      `event: optimization\ndata: ${JSON.stringify(payload)}\n\n`,
    ])));
    const onOptimization = vi.fn();
    await streamSessionEvents('session', { onDelta: vi.fn(), onOptimization }, new AbortController().signal, null);
    expect(onOptimization).toHaveBeenCalledWith(expect.objectContaining({
      result: { outcome: 'optimal', score: 0, solverStatus: 'OPTIMAL', terminationReason: 'completed' },
      request: { solver: 'ortools/cp-sat', timeoutSeconds: 300 },
      backend: expect.objectContaining({ url: 'http://optimizer:8000', appVersion: 'v0.4.3', requestTimeoutSeconds: 30,
        claimedPerformance: { score: 125, appVersion: 'v0.4.2', measuredAt: '2026-09-18T01:00:00Z' } }),
    }));
  });

  it('streams optimizer-triggered runs with authentication', async () => {
    const fetchMock = vi.fn().mockResolvedValue(streamedResponse([
      'id: 1\nevent: optimization\ndata: {"job_id":"opt-1","state":"running","terminal":false,"downloadable":false}\n\n',
      'id: 2\nevent: optimization_progress\ndata: {"job_id":"opt-1","progress":{"currentBestScore":23,"elapsedSeconds":2,"source":"solver"}}\n\n',
      'id: 3\nevent: run_start\ndata: {"run_id":"background-1","trigger":"optimizer"}\n\n',
      'id: 4\nevent: delta\ndata: {"text":"Score 23."}\n\n',
      'id: 5\nevent: done\ndata: {"run_id":"background-1"}\n\n',
    ]));
    vi.stubGlobal('fetch', fetchMock);
    const starts: string[] = [];
    const texts: string[] = [];
    const done = vi.fn();
    const optimizations = vi.fn();
    const progress = vi.fn();
    const eventIds: number[] = [];

    await streamSessionEvents(
      'session/id',
      {
        onRunStart: (runId, trigger) => starts.push(`${runId}:${trigger}`),
        onDelta: text => texts.push(text),
        onOptimization: optimizations,
        onOptimizationProgress: progress,
        onDone: done,
        onEventId: id => eventIds.push(id),
      },
      new AbortController().signal,
      'event-token',
    );

    expect(starts).toEqual(['background-1:optimizer']);
    expect(texts).toEqual(['Score 23.']);
    expect(done).toHaveBeenCalledWith('background-1');
    expect(eventIds).toEqual([1, 2, 3, 4, 5]);
    expect(optimizations).toHaveBeenCalledWith({
      jobId: 'opt-1',
      state: 'running',
      terminal: false,
      downloadable: false,
    });
    expect(progress).toHaveBeenCalledWith({
      jobId: 'opt-1',
      point: {
        currentBestScore: 23,
        elapsedSeconds: 2,
        source: 'solver',
        solutionIndex: null,
        commentCount: null,
      },
    });
    expect(fetchMock).toHaveBeenCalledWith(
      'https://api.nursescheduling.org/ai/sessions/session%2Fid/events',
      {
        method: 'GET',
        credentials: 'include',
        headers: { Authorization: 'Bearer event-token' },
        signal: expect.any(AbortSignal),
      },
    );
  });

  it('acknowledges a stale background turn instead of replaying it forever', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streamedResponse([
      'id: 7\nevent: delta\ndata: {"text":"Obsolete"}\n\n',
      'id: 8\nevent: stale\ndata: {"message":"The schedule changed."}\n\n',
    ])));
    const stale = vi.fn();
    const eventIds: number[] = [];

    await streamSessionEvents(
      'session-id',
      { onDelta: vi.fn(), onStale: stale, onEventId: id => eventIds.push(id) },
      new AbortController().signal,
      null,
    );

    expect(stale).toHaveBeenCalledWith('The schedule changed.');
    expect(eventIds).toEqual([7, 8]);
  });

  it('resumes background events after the stored cursor', async () => {
    const fetchMock = vi.fn().mockResolvedValue(streamedResponse([]));
    vi.stubGlobal('fetch', fetchMock);

    await streamSessionEvents(
      'session-id',
      { lastEventId: 4, onDelta: vi.fn() },
      new AbortController().signal,
      null,
    );

    expect(fetchMock).toHaveBeenCalledWith(
      'https://api.nursescheduling.org/ai/sessions/session-id/events',
      expect.objectContaining({ headers: { 'Last-Event-ID': '4' } }),
    );
  });

  it('deduplicates replay and identifies a turn without its retained start event', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streamedResponse([
      'id: 4\nevent: delta\ndata: {"text":"old","run_id":"old-turn"}\n\n',
      'id: 5\nevent: delta\ndata: {"text":"new","run_id":"new-turn"}\n\n',
      'id: 5\nevent: delta\ndata: {"text":"duplicate","run_id":"new-turn"}\n\n',
    ])));
    const delta = vi.fn();
    const context = vi.fn();
    const cursor = vi.fn();
    await streamSessionEvents('session', {
      lastEventId: 4, onDelta: delta, onRunContext: context, onEventId: cursor,
    }, new AbortController().signal, null);
    expect(delta).toHaveBeenCalledExactlyOnceWith('new');
    expect(context).toHaveBeenCalledExactlyOnceWith('new-turn');
    expect(cursor).toHaveBeenCalledExactlyOnceWith(5);
  });

  it('does not acknowledge a replayable event before receiving its delimiter', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streamedResponse([
      'id: 6\r\nevent: delta\r\ndata: {"text":"complete"}\r',
      '\n\r\n',
      'id: 7\nevent: delta\ndata: {"text":"replay me"}\n',
    ])));
    const delta = vi.fn();
    const cursor = vi.fn();
    await streamSessionEvents('session', { onDelta: delta, onEventId: cursor }, new AbortController().signal, null);
    expect(delta).toHaveBeenCalledExactlyOnceWith('complete');
    expect(cursor).toHaveBeenCalledExactlyOnceWith(6);
  });

  it('stops a session turn with authentication', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 202 }));
    vi.stubGlobal('fetch', fetchMock);

    await stopSession('session/id', 'result-token');

    expect(fetchMock).toHaveBeenCalledWith(
      'https://api.nursescheduling.org/ai/sessions/session%2Fid/stop',
      {
        method: 'POST',
        credentials: 'include',
        headers: { Authorization: 'Bearer result-token' },
      },
    );
  });

  it('downloads an optimizer result with authentication', async () => {
    // Build the body from text. A jsdom Blob is not always a body the runtime's
    // Response accepts, which made this check fail on some platforms only.
    const fetchMock = vi.fn().mockResolvedValue(new Response('workbook', {
      status: 200,
      headers: { 'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' },
    }));
    vi.stubGlobal('fetch', fetchMock);

    const workbook = await downloadOptimization('session/id', 'opt/id', 'result-token');
    expect(await workbook.text()).toBe('workbook');
    expect(workbook.type).toBe('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');

    expect(fetchMock).toHaveBeenCalledWith(
      'https://api.nursescheduling.org/ai/sessions/session%2Fid/optimizations/opt%2Fid/xlsx',
      {
        method: 'GET',
        credentials: 'include',
        headers: { Authorization: 'Bearer result-token' },
      },
    );
  });

  it('queues a steering message without cancelling the active stream', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 202 }));
    vi.stubGlobal('fetch', fetchMock);

    await queueMessage('session/id', 'queued-1', 'Focus on P2.', 'stream-token');

    expect(fetchMock).toHaveBeenCalledWith(
      'https://api.nursescheduling.org/ai/sessions/session%2Fid/messages/queue',
      {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json', Authorization: 'Bearer stream-token' },
        body: JSON.stringify({ message_id: 'queued-1', message: 'Focus on P2.' }),
      },
    );
  });

  it('approves a proposal with the revision the browser holds', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ schedule_yaml: 'description: approved\n' }),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    ));
    vi.stubGlobal('fetch', fetchMock);

    await expect(approveProposal('session-id', 'description: test', 'proposal-token')).resolves.toBe(
      'description: approved\n',
    );
    expect(fetchMock).toHaveBeenCalledWith('https://api.nursescheduling.org/ai/sessions/session-id/proposal/approve', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', Authorization: 'Bearer proposal-token' },
      body: JSON.stringify({ base_sha256: await scheduleRevision('description: test') }),
    });
  });

  it('reports the backend reason when a proposal cannot be approved', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: 'The schedule changed after this proposal was created, so it was discarded.' }),
      { status: 409, headers: { 'Content-Type': 'application/json' } },
    )));

    await expect(approveProposal('session-id', 'description: test', null)).rejects.toThrow(
      'The schedule changed after this proposal was created, so it was discarded.',
    );
  });

  it('rejects a proposal and refreshes a session schedule', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal('fetch', fetchMock);

    await rejectProposal('session-id', 'session-token');
    await updateSessionSchedule('session-id', 'description: newer', 'session-token');

    expect(fetchMock.mock.calls[0][0]).toBe('https://api.nursescheduling.org/ai/sessions/session-id/proposal/reject');
    expect(fetchMock.mock.calls[0][1]).toMatchObject({
      headers: { Authorization: 'Bearer session-token' },
    });
    expect(fetchMock.mock.calls[1][0]).toBe('https://api.nursescheduling.org/ai/sessions/session-id/schedule');
    expect(fetchMock.mock.calls[1][1]).toMatchObject({
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', Authorization: 'Bearer session-token' },
      body: JSON.stringify({ schedule_yaml: 'description: newer' }),
    });
  });

  it('treats a tool event without detail as a successful call', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streamedResponse([
      'event: tool\ndata: {"name":"bash"}\n\n',
      'event: done\ndata: {"run_id":"1"}\n\n',
    ])));
    const tools: { name: string; ok: boolean; result: string }[] = [];

    await streamMessage('session-id', 'Look.', { onDelta: () => {}, onTool: activity => tools.push(activity) },
      new AbortController().signal, null);

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
      null,
    )).rejects.toThrow('The AI backend returned an invalid schedule change.');
  });

  it('recognizes the official AI endpoints regardless of spelling', () => {
    expect(isOfficialAiEndpoint(PRODUCTION_AI_API_URL)).toBe(true);
    expect(isOfficialAiEndpoint('/ai')).toBe(true);
    expect(isOfficialAiEndpoint('api.nursescheduling.org/ai/')).toBe(true);
    expect(isOfficialAiEndpoint('https://ai.example.test')).toBe(false);
    expect(isOfficialAiEndpoint('')).toBe(false);
  });
});
