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

import { expect, test, type Page } from '@playwright/test';
import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process';
import { mkdir, writeFile } from 'node:fs/promises';
import { createServer, type ServerResponse } from 'node:http';
import type { AddressInfo } from 'node:net';
import path from 'node:path';
import { createInterface } from 'node:readline';
import fixture from '../../core/tests/ai_fixtures/chat-rendering.json';

const root = path.resolve(__dirname, '../..');
const storageKey = 'nurse-scheduling-ai-conversation';
type SavedEvent = { type: string; occurred_at: number; data: Record<string, unknown> };
type SavedRun = Omit<typeof fixture.runs[number], 'finished_at'> & { finished_at: number | null };
type Snapshot = Omit<typeof fixture, 'events' | 'runs'> & { events: SavedEvent[]; runs: SavedRun[] };
const variants = ['rich', 'empty', 'pending', 'pending-tool', 'stopped', 'truncated', 'failed-truncated', 'final-truncated',
  'length-recovery', 'tool-rounds', 'failed-summary', 'manual-completed', 'manual-failed', 'manual-skipped', 'manual-interrupted',
  'manual-running'] as const;

let renderer: ChildProcessWithoutNullStreams;
let replies: AsyncIterator<string>;
let rendererStderr = '';

async function renderingReply(timeoutMs = 15_000): Promise<string> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    return await Promise.race([
      replies.next().then(({ value, done }) => {
        if (done) throw new Error(`Python rendering helper exited: ${rendererStderr}`);
        return JSON.parse(value) as string;
      }),
      new Promise<string>((_, reject) => {
        timer = setTimeout(() => {
          renderer.kill();
          reject(new Error(`Python rendering helper timed out: ${rendererStderr}`));
        }, timeoutMs);
      }),
    ]);
  } finally {
    clearTimeout(timer);
  }
}

test.beforeAll(async () => {
  test.setTimeout(60_000);
  renderer = spawn(process.env.AI_EXPORT_PYTHON ?? 'python', ['-u', '-m', 'tests.chat_rendering_helper', 'worker'], {
    cwd: path.join(root, 'core'), stdio: 'pipe',
  });
  renderer.stderr.on('data', chunk => { rendererStderr = (rendererStderr + chunk.toString()).slice(-8000); });
  renderer.on('error', error => { rendererStderr += error.message; });
  renderer.stdin.on('error', error => { rendererStderr += error.message; });
  replies = createInterface({ input: renderer.stdout })[Symbol.asyncIterator]();
  // Give the one cold import its own setup budget. Individual requests keep their deadline.
  expect(await renderingReply(45_000)).toBe('ready');
});

test.afterAll(async () => {
  if (!renderer || renderer.exitCode !== null || renderer.signalCode !== null) return;
  const exited = new Promise<void>(resolve => renderer.once('exit', () => resolve()));
  renderer.kill();
  await exited;
});

async function renderingRequest(request: Record<string, unknown>, timeoutMs = 15_000): Promise<string> {
  await new Promise<void>((resolve, reject) => {
    renderer.stdin.write(JSON.stringify(request) + '\n', error => error ? reject(error) : resolve());
  });
  return renderingReply(timeoutMs);
}

function scenario(variant: typeof variants[number]): Snapshot {
  const snapshot: Snapshot = structuredClone(fixture);
  if (variant === 'rich') {
    const completion = snapshot.events.find(event => event.type === 'optimization')!;
    Object.assign(completion.data, { elapsed_seconds: 83, finish_now_requested_by: 'user',
      started_at: '2026-10-30T00:00:10Z', finished_at: '2026-10-30T00:01:33Z' });
    return snapshot;
  }
  const run = snapshot.runs[0];
  snapshot.runs = [run];
  snapshot.events = snapshot.events.slice(0, snapshot.events.findIndex(event => event.type === 'reasoning'));
  if (variant === 'pending' || variant === 'empty') {
    const call = snapshot.events.findLast(event => event.type === 'provider_call')!;
    Object.assign(call.data, { status: 'pending', cost_usd: null, usage: null, provider_call_id: null,
      streaming_seconds: null, time_to_first_output_seconds: null });
    const totals = { usd: '0.012340001', calls: 3, pending: 1, unavailable: 0,
      streaming: { calls: 1, output_tokens: 578, seconds: 2.89 } };
    const summary = snapshot.events.find(event => event.type === 'cost_summary')!;
    Object.assign(summary.data, { conversation: totals, run: totals });
    snapshot.events.find(event => event.type === 'model_selection')!.data.reasoning = 'default';
  }
  let at = snapshot.events.at(-1)!.occurred_at;
  const append = (type: string, data: Record<string, unknown> = {}) => {
    at += 250;
    snapshot.events.push({ type, data: { run_id: snapshot.runs.at(-1)!.id, ...data }, occurred_at: at });
    snapshot.snapshot_at = at;
  };
  if (variant.startsWith('manual-')) {
    append('delta', { text: 'Ready to summarize.' }); append('done');
    run.finished_at = at;
    at += 1000;
    snapshot.runs.push({ ...run, id: 'manual-compaction', kind: 'compaction', prompt: '', started_at: at, status: 'running', finished_at: null });
    append('run_start', { trigger: 'compaction' });
    snapshot.runs.at(-1)!.started_at = at;
    append('compaction_start', { reason: 'manual', tokens_before: 25000 });
    append('generation_progress', { kind: 'compaction', characters: 41, step: 2 });
    if (variant !== 'manual-running') {
      append('compaction_end', { reason: 'manual', tokens_before: 25000, success: variant === 'manual-completed',
        aborted: variant === 'manual-interrupted', skipped: variant === 'manual-skipped',
        ...(variant === 'manual-completed' ? { summary: 'Retain Alice and Bob.', keep_messages: 0 } : {}) });
      append(variant === 'manual-interrupted' ? 'stopped' : 'done');
    }
  } else if (variant === 'failed-summary') {
    append('compaction_end', { reason: 'overflow', tokens_before: 25000, success: true, aborted: false,
      summary: 'A summary that must be discarded.', keep_messages: 1 });
    append('delta', { text: 'Earlier completed reply.' });
    append('steering', { message_id: 'steer-failed', message: 'Now change the schedule.' });
    append('delta', { text: 'Partial failed reply.' });
    append('response_end', { stop_reason: 'error', context_note: '[App event] The workspace was discarded.' });
    append('error', { message: 'The provider failed.' });
  } else if (variant === 'stopped') {
    append('tool_start', { name: 'bash', tool_call_id: 'interrupted', arguments: '{"command":"sleep 30"}' });
    append('reasoning', { text: 'Waiting for the command.' });
    append('delta', { text: 'Partial answer before Stop.' });
    append('response_end', { stop_reason: 'aborted' }); append('stopped');
  } else if (variant === 'pending-tool') {
    append('generation_progress', { kind: 'tool_calls', characters: 99, step: 1 });
  } else if (variant === 'truncated' || variant === 'failed-truncated') {
    append('reasoning', { text: 'Preparing the answer.' });
    append('delta', { text: 'The answer reached its token limit.' });
    append('response_end', { stop_reason: 'length' });
    if (variant === 'failed-truncated') append('error', { message: 'The follow-up provider request failed.' });
    else append('done');
  } else if (variant === 'final-truncated') {
    append('delta', { text: 'The final answer reached its token limit.' });
    append('truncated'); append('done');
  } else if (variant === 'length-recovery') {
    append('delta', { text: 'Partial plan before the length stop.' });
    append('response_end', { stop_reason: 'length', context_omitted: true });
    append('compaction_start', { reason: 'overflow', tokens_before: 25000 });
    append('compaction_end', { reason: 'overflow', tokens_before: 25000, success: true, aborted: false,
      summary: 'Retain Alice and Bob.', keep_messages: 1 });
    append('delta', { text: 'Recovered answer.' });
    append('done');
  } else if (variant === 'tool-rounds') {
    // Two tool-only rounds send four model messages. The summary keeps them and compacts the upload notice and question.
    for (const id of ['first', 'second']) {
      append('response_end', { stop_reason: 'tool_use' });
      append('tool_start', { name: 'read', tool_call_id: id, arguments: '{"path":"staff.csv"}' });
      append('tool', { name: 'read', tool_call_id: id, arguments: '{"path":"staff.csv"}', result: 'Alice,Bob', ok: true });
    }
    append('compaction_start', { reason: 'threshold', tokens_before: 25000 });
    append('compaction_end', { reason: 'threshold', tokens_before: 25000, success: true, aborted: false,
      summary: 'Retain Alice and Bob.', keep_messages: 4 });
    append('delta', { text: 'Checked staff.csv twice.' }); append('done');
  } else if (variant === 'empty') append('done');
  const last = snapshot.runs.at(-1)!;
  const terminal = snapshot.events.at(-1)!;
  last.status = terminal.type === 'stopped' ? 'cancelled' : terminal.type === 'error' ? 'failed' : terminal.type === 'done' ? 'completed' : 'running';
  last.finished_at = last.status === 'running' ? null : terminal.occurred_at;
  return snapshot;
}

// Exercise the current production renderer, independently of frozen export bytes.
function exportHtml(snapshot: Snapshot): Promise<string> {
  return renderingRequest({ action: 'render', snapshot });
}

async function startBackend(origin: string, snapshot: Snapshot) {
  let stream: ServerResponse | undefined;
  let accepted = 0;
  let scheduleYaml = '';
  const requests = new Map<string, string>();
  const journal: string[] = [];
  const server = createServer(async (request, response) => {
    let requestBody = '';
    for await (const chunk of request) requestBody += chunk;
    const sent = requestBody ? JSON.parse(requestBody) : {};
    if (typeof sent.schedule_yaml === 'string') scheduleYaml = sent.schedule_yaml;
    response.setHeader('Access-Control-Allow-Origin', origin);
    response.setHeader('Access-Control-Allow-Credentials', 'true');
    response.setHeader('Access-Control-Allow-Headers', 'Content-Type, Last-Event-ID');
    response.setHeader('Access-Control-Allow-Methods', 'GET, POST, PATCH, PUT, DELETE, OPTIONS');
    if (request.method === 'OPTIONS') { response.writeHead(204).end(); return; }
    const url = new URL(request.url!, 'http://localhost');
    let body: unknown = {};
    if (url.pathname.endsWith('/capabilities')) body = {
      app_version: 'test', auth: { required: false, scheme: 'bearer' }, saved_chat_export: true,
      session_retention_seconds: 172800,
      file_attachments: { enabled: true, retained: true, max_files: 8, max_bytes_per_file: 5000000, max_bytes_per_session: 200000000 },
    };
    else if (url.pathname.endsWith('/sessions')) { response.statusCode = 201; body = { id: snapshot.session_id }; }
    else if (url.pathname.endsWith('/messages')) {
      const previous = requests.get(sent.message_id);
      const run = previous ? snapshot.runs.find(run => run.id === previous)! : snapshot.runs.filter(run => run.kind === 'foreground')[accepted++];
      requests.set(sent.message_id, run.id);
      const input = snapshot.events.find(event => event.type === 'model_input' && event.data.run_id === run.id)!;
      // Save the schedule actually accepted by the mock service, as production does.
      input.data.schedule_yaml = scheduleYaml;
      body = { run_id: run.id };
      response.statusCode = 202;
    } else if (url.pathname.endsWith('/compact')) {
      body = { run_id: 'manual-compaction' }; response.statusCode = 202;
    } else if (url.pathname.endsWith('/events')) {
      stream = response;
      response.writeHead(200, { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache' });
      response.flushHeaders();
      journal.slice(Number(request.headers['last-event-id'] ?? 0)).forEach(frame => response.write(frame));
      return;
    } else if (url.pathname.endsWith('/uploads')) body = [];
    else body = { expires_in_seconds: 172800 };
    response.setHeader('Content-Type', 'application/json'); response.end(JSON.stringify(body));
  });
  await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve));
  return {
    endpoint: `http://127.0.0.1:${(server.address() as AddressInfo).port}/ai`,
    get connected() { return !!stream; },
    get accepted() { return accepted; },
    publish(event: SavedEvent) {
      const id = journal.length + 1;
      const frame = `id: ${id}\nevent: ${event.type}\ndata: ${JSON.stringify(event.data)}\n\n`;
      journal.push(frame); stream?.write(frame); return id;
    },
    async close() {
      const done = new Promise<void>((resolve, reject) => server.close(error => error ? reject(error) : resolve()));
      server.closeAllConnections(); await done;
    },
  };
}

async function replay(page: Page, snapshot: Snapshot, backend: Awaited<ReturnType<typeof startBackend>>) {
  let sent = 0;
  for (const event of snapshot.events) {
    await page.clock.setFixedTime(event.occurred_at);
    if (event.type === 'run_start') {
      const run = snapshot.runs.find(run => run.id === event.data.run_id)!;
      if (run.kind === 'compaction') {
        await page.getByRole('button', { name: 'Compact context', exact: true }).click();
      } else if (run.kind === 'foreground') {
        await page.getByRole('textbox', { name: 'Ask about the current schedule' }).fill(run.prompt);
        await page.getByRole('button', { name: 'Send', exact: true }).click();
        await expect.poll(() => backend.accepted).toBe(++sent);
        // Cover a slow first event that arrives after the accepted request was saved.
        await page.waitForFunction(({ storageKey, runId }) => {
          const stored = sessionStorage.getItem(storageKey);
          return stored && JSON.parse(stored).messages.some((message: { runId?: string }) => message.runId === runId);
        }, { storageKey, runId: run.id });
      }
      await expect.poll(() => backend.connected).toBe(true);
    }
    const id = backend.publish(event);
    // Cursor-only events need not rerender or schedule another debounced save.
    // Flush through the real page-hide path before checking browser persistence.
    await page.waitForFunction(({ storageKey, id }) => {
      window.dispatchEvent(new Event('pagehide'));
      const stored = sessionStorage.getItem(storageKey);
      return stored && JSON.parse(stored).sessionEventId === id;
    }, { storageKey, id }, { timeout: 5000 }).catch(error => {
      throw new Error(`Event ${id} (${event.type}) was not applied`, { cause: error });
    });
  }
}

async function contentState(page: Page) {
  return page.locator('article').evaluateAll(articles => articles.map(article => {
    const copy = article.cloneNode(true) as HTMLElement;
    copy.querySelectorAll('[data-live-action], time').forEach(element => element.remove());
    return {
      text: copy.textContent?.replace(/\s+/g, ''),
      raw: Array.from(copy.querySelectorAll('pre')).map(element => element.textContent),
      disclosures: Array.from(copy.querySelectorAll('details')).map(details => ({
        label: details.querySelector('summary')?.textContent?.trim(), open: details.open,
      })),
      times: Array.from(article.querySelectorAll('time')).map(time => ({
        instant: time.dateTime, duration: time.textContent?.split(' · ')[1] ?? null,
      })),
    };
  }));
}

async function appearanceState(page: Page) {
  return page.locator('.chat').evaluate(section => {
    const properties = ['font-family', 'font-size', 'font-weight', 'line-height', 'color', 'background-color',
      'border-color', 'border-width', 'border-style', 'border-radius', 'padding', 'letter-spacing',
      'white-space', 'overflow-wrap', 'word-break', 'max-height', 'text-align', 'text-transform'];
    return Array.from(section.querySelectorAll(
      'article, .label, .message-status, summary, pre, .cost-call, .model-selection, article time, .optimizer-details, .optimizer-label',
    )).map(element => {
      const style = getComputedStyle(element);
      return Object.fromEntries(properties.map(property => [property, style.getPropertyValue(property)]));
    });
  });
}

async function compareTranscript(page: Page, exported: Page, dir: string, state: string) {
  expect(await contentState(exported)).toEqual(await contentState(page));
  for (const width of [900, 390]) {
    for (const current of [page, exported]) {
      await current.setViewportSize({ width, height: 900 });
      await current.locator('.chat').evaluate((section, width) => {
        // Only the surrounding app/document layout differs between these views.
        let frame = document.querySelector<HTMLElement>('[data-render-frame]');
        if (!frame) {
          frame = document.createElement('div');
          frame.dataset.renderFrame = '';
          document.body.append(frame);
          frame.append(section);
        }
        // Hide the rest of the page. Otherwise the live page paints its app into the transcript's layer,
        // and macOS GPU raster can antialias the transcript differently.
        for (const child of Array.from(document.body.children)) {
          if (child !== frame) (child as HTMLElement).style.display = 'none';
        }
        Object.assign(frame.style, { position: 'absolute', top: '0', left: '0', width: `${width}px`, background: 'white' });
        Object.assign((section as HTMLElement).style, {
          width: `${width}px`, margin: '0', minHeight: '0', height: 'auto',
        });
        for (const child of Array.from(section.children)) {
          if (child.tagName !== 'ARTICLE') (child as HTMLElement).style.display = 'none';
        }
        section.querySelectorAll<HTMLElement>('[data-live-action]').forEach(element => { element.style.display = 'none'; });
        // React inserts comments between text fragments. Join equivalent text runs.
        const comments = document.createTreeWalker(section, NodeFilter.SHOW_COMMENT);
        const removed: Node[] = [];
        while (comments.nextNode()) removed.push(comments.currentNode);
        removed.forEach(node => node.parentNode!.removeChild(node));
        section.normalize();
        section.querySelectorAll('time').forEach(time => {
          // Offline exports use UTC. Verify the instant above, then normalize display for pixels.
          time.textContent = time.getAttribute('datetime') + (time.textContent?.includes(' · ') ? ` · ${time.textContent.split(' · ')[1]}` : '');
        });
        // Use integer outer bounds so browser clipping does not blend a half-pixel border.
        (section as HTMLElement).style.height = `${Math.ceil(section.getBoundingClientRect().height)}px`;
      }, width);
    }
    await Promise.all([page.mouse.move(width - 1, 0), exported.mouse.move(width - 1, 0)]);
    expect(await appearanceState(exported)).toEqual(await appearanceState(page));
    const screenshotStyle = '.chat > :not(article), [data-live-action] { display: none !important; }';
    const [livePng, exportPng] = await Promise.all([
      page.locator('.chat').screenshot({ animations: 'disabled', style: screenshotStyle }),
      exported.locator('.chat').screenshot({ animations: 'disabled', style: screenshotStyle }),
    ]);
    const prefix = path.join(dir, `${state}-${width}`);
    await Promise.all([writeFile(`${prefix}-frontend.png`, livePng), writeFile(`${prefix}-export.png`, exportPng)]);
    const difference = await renderingRequest({ action: 'compare', frontend: `${prefix}-frontend.png`,
      export: `${prefix}-export.png`, difference: `${prefix}-diff.png` }, 10_000);
    expect(difference, `${state}, ${width}px. Compare ${prefix}-*.png`).toBe('identical');
  }
}

test.use({ locale: 'en-US', timezoneId: 'UTC' });

for (const variant of variants) test(`current Python export follows the live transcript: ${variant}`, async ({ page, context, baseURL }) => {
  test.setTimeout(90_000);
  const snapshot = scenario(variant);
  const backend = await startBackend(new URL(baseURL!).origin, snapshot);
  const exported = await context.newPage();
  const externalRequests: string[] = [];
  await exported.route('**/*', route => { externalRequests.push(route.request().url()); return route.abort(); });
  const dir = path.join(root, 'artifacts', 'chat-rendering', test.info().project.name, variant);
  await mkdir(dir, { recursive: true });
  try {
    await page.clock.setFixedTime(snapshot.runs[0].started_at);
    await page.addInitScript(endpoint => localStorage.setItem('nurse-scheduling-ai-server', endpoint), backend.endpoint);
    await page.goto('/experimental-ai');
    for (const name of ['Show reasoning', 'Show tool activity', 'Show turn details', 'Show models']) {
      await page.getByRole('checkbox', { name, exact: true }).check();
    }
    await replay(page, snapshot, backend);
    if (variant === 'rich') {
      await expect(page.getByRole('button', { name: 'Download files (ZIP)', exact: true })).toHaveCount(1);
    }
    await exported.setContent(await exportHtml(snapshot));
    await expect(exported.locator('script')).toHaveCount(0);
    if (variant === 'length-recovery') {
      for (const current of [page, exported]) {
        await expect(current.getByText('Incomplete response. Omitted from future model context.')).toHaveCount(1);
      }
    }
    if (variant === 'tool-rounds') {
      for (const current of [page, exported]) {
        await expect(current.getByText('Compacted out of context.')).toHaveCount(2);
      }
    }
    await Promise.all([
      writeFile(path.join(dir, 'frontend-original.html'), await page.content()),
      writeFile(path.join(dir, 'export-original.html'), await exported.content()),
      writeFile(path.join(dir, 'snapshot.json'), JSON.stringify(snapshot, null, 2)),
    ]);
    const cost = exported.locator('details').filter({ has: exported.locator('summary', { hasText: /^Turn details ·/ }) }).first();
    await expect(cost).toHaveCount(1);
    await expect(cost).not.toHaveAttribute('open', '');
    await cost.locator('summary').click();
    await expect(cost.getByRole('list', { name: 'Provider calls' })).toBeVisible();
    await cost.locator('summary').click();
    await compareTranscript(page, exported, dir, 'collapsed');
    for (const current of [page, exported]) {
      for (const disclosure of await current.locator('article details').all()) {
        if (!(await disclosure.evaluate(element => (element as HTMLDetailsElement).open))) {
          await disclosure.locator(':scope > summary').click();
        }
      }
    }
    await compareTranscript(page, exported, dir, 'expanded');
    const articles = await page.locator('article').count();
    await page.reload();
    await exported.setContent(await exportHtml(snapshot));
    await expect(page.locator('article')).toHaveCount(articles);
    await compareTranscript(page, exported, dir, 'reloaded');
    expect(externalRequests).toEqual([]);
  } finally {
    await Promise.allSettled([
      page.content().then(html => writeFile(path.join(dir, 'frontend.html'), html)),
      exported.content().then(html => writeFile(path.join(dir, 'export.html'), html)),
    ]);
    await backend.close(); await exported.close();
  }
});
