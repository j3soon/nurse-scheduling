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

import { spawn, spawnSync, type ChildProcess } from 'node:child_process';
import { createServer } from 'node:net';
import { networkInterfaces } from 'node:os';
import { expect, test as base } from '@playwright/test';

// The development server compiles on demand and competes with the other
// workers, so allow far more than the Playwright default. Keep the test budget
// strictly larger than the readiness budget so a slow start reports the
// captured server logs instead of a bare test timeout.
const TEST_TIMEOUT_MS = 180_000;
const SERVER_READY_TIMEOUT_MS = 90_000;
const SERVER_STOP_TIMEOUT_MS = 5_000;

function nonLoopbackIpv4(): string | undefined {
  return Object.values(networkInterfaces())
    .flatMap(addresses => addresses ?? [])
    .find(address => address.family === 'IPv4' && !address.internal)
    ?.address;
}

// Use an ephemeral port so a leftover server can never fail a later retry.
function reservePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const probe = createServer();
    probe.once('error', reject);
    probe.listen(0, '0.0.0.0', () => {
      const address = probe.address();
      if (address === null || typeof address === 'string') {
        probe.close(() => reject(new Error('Failed to reserve a development server port.')));
        return;
      }
      const { port } = address;
      probe.close(() => resolve(port));
    });
  });
}

async function waitForServer(url: string, processExited: Promise<number | null>, logs: () => string): Promise<void> {
  const deadline = Date.now() + SERVER_READY_TIMEOUT_MS;
  const exited = processExited.then(code => {
    throw new Error(`Next.js development server exited with ${code}.\n${logs()}`);
  });
  // Nothing observes this once the server is ready, so keep the eventual
  // rejection from surfacing as an unhandled rejection during teardown.
  exited.catch(() => {});
  while (Date.now() < deadline) {
    const result = await Promise.race([
      fetch(url, { signal: AbortSignal.timeout(1_000) }).then(response => response.ok).catch(() => false),
      exited,
    ]);
    if (result) return;
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw new Error(`Next.js development server did not become ready.\n${logs()}`);
}

// Kill `next dev` as well as the `bun` wrapper that spawned it.
function killServerTree(server: ChildProcess, signal: NodeJS.Signals): void {
  if (!server.pid) return;

  if (process.platform === 'win32') {
    // Windows has no process groups, so walk the tree explicitly.
    spawnSync('taskkill', ['/pid', String(server.pid), '/t', '/f']);
    return;
  }

  try {
    // `detached` makes the child a group leader, so this reaches `next dev` too.
    process.kill(-server.pid, signal);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== 'ESRCH') throw error;
  }
}

function exitedWithin(processExited: Promise<number | null>, timeoutMs: number): Promise<boolean> {
  return new Promise(resolve => {
    const timer = setTimeout(() => resolve(false), timeoutMs);
    processExited.then(() => {
      clearTimeout(timer);
      resolve(true);
    });
  });
}

async function stopServer(server: ChildProcess, processExited: Promise<number | null>): Promise<void> {
  if (server.exitCode !== null || server.signalCode !== null) return;
  killServerTree(server, 'SIGTERM');
  if (await exitedWithin(processExited, SERVER_STOP_TIMEOUT_MS)) return;
  killServerTree(server, 'SIGKILL');
  await exitedWithin(processExited, SERVER_STOP_TIMEOUT_MS);
}

type DevServerFixtures = {
  devServer: { host: string; port: number };
};

// Own the server from a fixture because Playwright still runs fixture teardown
// after a test times out. A `try`/`finally` in the test body does not run, which
// orphans the server and makes every retry fail to bind.
const test = base.extend<DevServerFixtures>({
  // `use` is renamed because the React hooks lint rule misreads that name.
  devServer: async ({}, runTest, testInfo) => {
    testInfo.setTimeout(TEST_TIMEOUT_MS);
    const host = nonLoopbackIpv4();
    testInfo.skip(!host, 'A non-loopback IPv4 address is required.');
    if (host === undefined) return;

    const port = await reservePort();
    const output: string[] = [];
    const server = spawn(
      'bun',
      ['run', 'dev', '--hostname', '0.0.0.0', '--port', String(port)],
      {
        cwd: process.cwd(),
        detached: process.platform !== 'win32',
        env: {
          ...process.env,
          DISABLE_SENTRY: '1',
          NEXT_PUBLIC_DISABLE_SENTRY: '1',
          NEXT_TELEMETRY_DISABLED: '1',
        },
        stdio: ['ignore', 'pipe', 'pipe'],
      },
    );
    server.stdout.on('data', chunk => output.push(String(chunk)));
    server.stderr.on('data', chunk => output.push(String(chunk)));
    const processExited = new Promise<number | null>(resolve => server.once('exit', resolve));

    try {
      await waitForServer(`http://127.0.0.1:${port}/experimental-ai`, processExited, () => output.join(''));
      await runTest({ host, port });
    } finally {
      await stopServer(server, processExited);
    }
  },
});

test('hydrates through a non-loopback development origin', async ({ page, devServer }) => {
  const { host, port } = devServer;

  await page.route(`http://${host}:8001/capabilities`, route => route.fulfill({
    status: 200,
    contentType: 'application/json',
    headers: {
      'Access-Control-Allow-Credentials': 'true',
      'Access-Control-Allow-Origin': `http://${host}:${port}`,
    },
    body: JSON.stringify({
      image_attachments: {
        enabled: true,
        accepted_media_types: ['image/png'],
        max_files: 1,
        max_bytes_per_file: 1000,
      },
      document_attachments: {
        enabled: true,
        accepted_extensions: ['.txt', '.md', '.csv', '.pdf', '.xlsx'],
        max_files: 1,
        max_bytes_per_file: 5000000,
      },
    }),
  }));

  await page.goto(`http://${host}:${port}/experimental-ai`);

  await expect(page.getByRole('textbox', { name: 'Ask about the current schedule' })).toBeEnabled();
  await expect(page.getByLabel('Attach files')).toBeAttached();
});
