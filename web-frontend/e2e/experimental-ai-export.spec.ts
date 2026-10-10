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

import { expect, test } from '@playwright/test';
import { readFile, readdir, writeFile, mkdir, mkdtemp } from 'node:fs/promises';
import { resolve } from 'node:path';
import { execFileSync, spawnSync } from 'node:child_process';
import snapshot from '../../core/tests/ai_fixtures/chat-export.json';

test.use({ timezoneId: 'Pacific/Honolulu', locale: 'zh-TW' });

for (const failure of ['json', 'snapshot', 'filesystem'] as const) {
  test(`CLI reports the ${failure} failure cause and preserves existing output`, async () => {
    await mkdir(resolve('../artifacts'), { recursive: true });
    const directory = await mkdtemp(resolve('../artifacts/chat-export-failure-'));
    const input = resolve(directory, 'snapshot.json');
    const output = resolve(directory, 'chat.md');
    const original = 'Existing output';
    await writeFile(input, failure === 'json' ? '{' : JSON.stringify({
      ...snapshot, schema_version: failure === 'snapshot' ? 2 : 1,
    }));
    if (failure === 'filesystem') await mkdir(output);
    const preserved = failure === 'filesystem' ? resolve(output, 'original.txt') : output;
    await writeFile(preserved, original);

    const result = spawnSync('bun', ['scripts/export-ai-chat.ts', output, '--snapshot', input], {
      cwd: resolve('.'), encoding: 'utf8', timeout: 10_000,
    });

    expect(result.error).toBeUndefined();
    expect(result.status).toBe(1);
    expect(result.stderr).toContain('The output file was not changed.');
    if (failure === 'filesystem') {
      // Renaming over a directory reports EISDIR on Unix and EPERM on Windows.
      expect(result.stderr).toMatch(/\b(?:EISDIR|EPERM):[^\n]*\brename\b/);
      expect(result.stderr).toContain(output);
    } else {
      expect(result.stderr).toMatch(failure === 'json' ? /JSON|Unexpected|Expected/ : /invalid saved chat snapshot/);
    }
    expect(await readFile(preserved, 'utf8')).toBe(original);
    expect((await readdir(directory)).filter(name => name.endsWith('.tmp'))).toEqual([]);
  });
}

test('saved HTML and Markdown browser downloads byte-match the backend CLI', async ({ page }) => {
  const fixture = resolve('../core/tests/ai_fixtures/chat-export.json');
  await mkdir(resolve('../artifacts'), { recursive: true });
  const outputDirectory = await mkdtemp(resolve('../artifacts/chat-export-'));
  await page.route('**/ai/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith('/capabilities')) {
      await route.fulfill({ json: {
        app_version: 'v0.4.3', saved_chat_export: true, session_retention_seconds: 3600,
        auth: { required: false, scheme: 'bearer' },
        file_attachments: { enabled: true, retained: true, max_files: 8, max_bytes_per_file: 5000000 },
      } });
    } else if (path.endsWith('/export')) {
      await route.fulfill({ json: snapshot });
    } else if (path.endsWith('/sessions')) {
      await route.fulfill({ status: 201, json: { id: snapshot.session_id } });
    } else if (path.endsWith('/uploads')) {
      await route.fulfill({ json: [] });
    } else if (path.endsWith('/events')) {
      await route.fulfill({ contentType: 'text/event-stream', body: [
        'id: 1\nevent: run_start\ndata: {"run_id":"export-run","trigger":"user"}\n\n',
        'id: 2\nevent: delta\ndata: {"run_id":"export-run","text":"Saved history is ready to export."}\n\n',
        'id: 3\nevent: done\ndata: {"run_id":"export-run"}\n\n',
      ].join('') });
    } else if (path.endsWith('/messages')) {
      await route.fulfill({ status: 202, json: { run_id: 'export-run' } });
    } else {
      await route.fulfill({ json: { expires_in_seconds: 3600 } });
    }
  });
  await page.goto('/experimental-ai');
  await page.getByRole('textbox', { name: 'Ask about the current schedule' }).fill('Export the saved chat.');
  await page.getByRole('button', { name: 'Send', exact: true }).click();
  await expect(page.getByText('Saved history is ready to export.')).toBeVisible();

  for (const format of ['html', 'markdown'] as const) {
    const output = resolve(outputDirectory, format === 'html' ? 'chat.html' : 'chat.md');
    execFileSync('bun', ['scripts/export-ai-chat.ts', output, '--snapshot', fixture], { cwd: resolve('.'), timeout: 10_000 });
    const download = page.waitForEvent('download');
    await page.getByRole('button', { name: format === 'html' ? 'HTML' : 'Markdown', exact: true }).click();
    const browserBytes = await readFile((await (await download).path())!);
    const backendBytes = await readFile(output);
    expect(browserBytes.equals(backendBytes)).toBe(true);
    const content = browserBytes.toString('utf8');
    expect(content).toContain('Command exited with code 7');
    expect(content).toContain('Keep the original names.');
    expect(content).toContain('Pending proposal');
    expect(content).not.toContain('Saved history is ready to export.');
  }
});
