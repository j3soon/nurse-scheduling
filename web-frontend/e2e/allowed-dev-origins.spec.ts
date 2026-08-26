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

import { spawn } from 'node:child_process';
import { networkInterfaces } from 'node:os';
import { expect, test } from '@playwright/test';

const DEV_PORT = 13005;

function nonLoopbackIpv4(): string | undefined {
  return Object.values(networkInterfaces())
    .flatMap(addresses => addresses ?? [])
    .find(address => address.family === 'IPv4' && !address.internal)
    ?.address;
}

async function waitForServer(url: string, processExited: Promise<number | null>, logs: () => string): Promise<void> {
  const deadline = Date.now() + 30_000;
  while (Date.now() < deadline) {
    const result = await Promise.race([
      fetch(url).then(response => response.ok).catch(() => false),
      processExited.then(code => {
        throw new Error(`Next.js development server exited with ${code}.\n${logs()}`);
      }),
    ]);
    if (result) return;
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw new Error(`Next.js development server did not become ready.\n${logs()}`);
}

test('hydrates through a non-loopback development origin', async ({ page }) => {
  const host = nonLoopbackIpv4();
  test.skip(!host, 'A non-loopback IPv4 address is required.');

  const output: string[] = [];
  const server = spawn(
    'bun',
    ['run', 'dev', '--hostname', '0.0.0.0', '--port', String(DEV_PORT)],
    {
      cwd: process.cwd(),
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
    await waitForServer(`http://127.0.0.1:${DEV_PORT}/experimental-ai`, processExited, () => output.join(''));
    await page.route(`http://${host}:8001/capabilities`, route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      headers: {
        'Access-Control-Allow-Credentials': 'true',
        'Access-Control-Allow-Origin': `http://${host}:${DEV_PORT}`,
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

    await page.goto(`http://${host}:${DEV_PORT}/experimental-ai`);

    await expect(page.getByRole('textbox', { name: 'Ask about the current schedule' })).toBeEnabled();
    await expect(page.getByLabel('Attach files')).toBeAttached();
  } finally {
    server.kill('SIGTERM');
    await Promise.race([
      processExited,
      new Promise(resolve => setTimeout(resolve, 5_000)),
    ]);
  }
});
