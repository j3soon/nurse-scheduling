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

import { existsSync, readFileSync, statSync } from 'node:fs';
import path from 'node:path';
import { expect, Locator, Page, Route, test } from '@playwright/test';
import yaml from 'js-yaml';
import { createMockXlsxBuffer } from '../e2e/helpers';

const IMAGES = path.join(__dirname, '../../docs/content/assets/images/user-guide');
const BUILD_REAL = path.join(IMAGES, 'build-a-real-schedule');
const APP_VERSION = process.env.APP_VERSION_OVERRIDE ?? '';
const EXAMPLE_NAME = 'large-ward-with-87-people-2025-11.yaml';
// Match the build version so imports show no version warning.
const EXAMPLE_YAML = readFileSync(path.join(__dirname, '../public/examples', EXAMPLE_NAME), 'utf8')
  .replace(/^appVersion: .*$/m, `appVersion: ${APP_VERSION}`);

// The schedule data that the Quick Start builds by hand.
const QUICK_START_YAML = yaml.dump({
  apiVersion: 'alpha',
  description: '',
  dates: { range: { startDate: '2026-08-01', endDate: '2026-08-07' }, groups: [] },
  people: { items: [{ id: 'P1', description: '', history: [] }], groups: [] },
  shiftTypes: { items: [{ id: 'D', description: '' }], groups: [] },
  preferences: [
    { type: 'at most one shift per day' },
    {
      type: 'shift type requirement', description: 'Daily day coverage', shiftType: ['D'],
      requiredNumPeople: 1, qualifiedPeople: ['ALL'], date: ['ALL'], weight: -1,
    },
    { type: 'shift request', person: ['P1'], date: ['01'], shiftType: ['D'], weight: 5 },
  ],
  appVersion: APP_VERSION,
});

// The walkthrough state right after the people upload: no people groups, history, or rules yet.
function exampleBeforePeopleGroups(): string {
  const data = yaml.load(EXAMPLE_YAML) as {
    people: { items: { history: unknown[] }[]; groups: unknown[] };
    preferences: { type: string }[];
  };
  data.people.groups = [];
  data.people.items.forEach(person => { person.history = []; });
  data.preferences = data.preferences.filter(preference => preference.type === 'at most one shift per day');
  return yaml.dump(data);
}

// Pages load from the production origin, as guide readers see them, but come from the exported build.
const SITE_ORIGIN = 'https://nursescheduling.org';
const EXPORT_DIR = path.join(__dirname, '../out');

// Resolve a request path like a static file server with clean URLs.
function exportedFile(pathname: string): string | null {
  const relative = decodeURIComponent(pathname).replace(/\/$/, '/index');
  for (const candidate of [relative, `${relative}.html`]) {
    const file = path.join(EXPORT_DIR, candidate);
    if (file.startsWith(EXPORT_DIR) && existsSync(file) && statSync(file).isFile()) return file;
  }
  return null;
}

// The app uses the platform's system font. Pin Arial-compatible fonts so captures look alike on every machine.
// Without transitions, focus and hover styles do not change between captures.
const CAPTURE_CSS = `
  * { font-family: "Liberation Sans", Arial, Helvetica, sans-serif !important; transition: none !important; }
  code, kbd, pre, samp, .font-mono, .font-mono * { font-family: "Liberation Mono", "Courier New", monospace !important; }
`;
// Hide the fixed tab arrows when they would overlap a cropped element.
const HIDE_TAB_ARROWS = 'button[title^="Previous tab"], button[title^="Next tab"] { visibility: hidden !important; }';
// A fixed clock keeps timestamps and download names stable between captures.
const FIXED_TIME = new Date('2026-08-05T07:32:19Z');
const BACKEND_URL = /^(http:\/\/localhost:8000|https:\/\/api(-secondary)?\.nursescheduling\.org)\//;
// Match the backend's job ID and workbook name formats.
const JOB_ID = 'job_31853c929f754c01aa81aba3fb969b91';
const WORKBOOK_NAME = 'nurse-scheduling-20260805T073220Z.xlsx';
// AI requests send credentials, so allow the site origin explicitly.
const CORS_HEADERS = {
  'Access-Control-Allow-Credentials': 'true',
  'Access-Control-Allow-Headers': 'Authorization, Content-Type',
  'Access-Control-Allow-Methods': 'GET, POST, DELETE, OPTIONS',
  'Access-Control-Allow-Origin': SITE_ORIGIN,
  'Access-Control-Expose-Headers': 'Content-Disposition',
};

function fulfillJson(route: Route, body: unknown) {
  return route.fulfill({ status: 200, headers: { ...CORS_HEADERS, 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
}

function job(completed: boolean) {
  return {
    id: JOB_ID,
    state: completed ? 'completed' : 'queued',
    terminal: completed,
    queue_position: completed ? null : 1,
    result: completed ? { outcome: 'optimal', score: 5, solver_status: 'OPTIMAL', termination_reason: null } : null,
    error: null,
    controls: { cancellable: !completed, early_completion_available: false },
    links: {
      self: `/optimize/${JOB_ID}`,
      events: `/optimize/${JOB_ID}/events`,
      cancellation: `/optimize/${JOB_ID}/cancel`,
      early_completion: `/optimize/${JOB_ID}/finish-now`,
      schedule: completed ? `/optimize/${JOB_ID}/xlsx` : null,
    },
  };
}

// Answer optimizer and AI requests like an idle compatible backend that solves at once.
async function mockBackend(route: Route, pathname: string) {
  const method = route.request().method();
  if (method === 'OPTIONS') return route.fulfill({ status: 204, headers: CORS_HEADERS });
  if (pathname === '/info') {
    return fulfillJson(route, {
      status: 'ready',
      service_name: 'nurse-scheduling-api',
      api_version: '0.2.0',
      app_version: APP_VERSION,
      auth: { required: false, scheme: 'bearer' },
      jobs: { running: 0, queued: 0, cancelling: 0 },
      workers: { online: 1 },
    });
  }
  if (pathname === '/ai/capabilities') {
    // The hosted AI beta requires an API key.
    return fulfillJson(route, {
      app_version: APP_VERSION,
      auth: { required: true, scheme: 'bearer' },
      file_attachments: { enabled: true, max_files: 8, max_bytes_per_file: 5_000_000, max_bytes_per_session: 200_000_000 },
    });
  }
  if (pathname === '/optimize/options') {
    return fulfillJson(route, {
      schema_version: 'alpha',
      solver: {
        default: 'ortools/cp-sat',
        choices: [{
          value: 'ortools/cp-sat',
          label: 'OR-Tools | CP-SAT',
          compute: 'cpu',
          timeout: { default: 300, minimum: 1, maximum: 3600 },
          controls: { cancel_running: true, finish_now: true },
        }],
      },
      prettify: { default: true },
    });
  }
  if (pathname === '/optimize' && method === 'POST') return fulfillJson(route, job(false));
  if (pathname === `/optimize/${JOB_ID}`) return fulfillJson(route, job(true));
  if (pathname === `/optimize/${JOB_ID}/events`) {
    // A real CP-SAT solve of the Quick Start schedule reports this one solution.
    const events = [
      ['job.progressed', { source: 'ortools/cp-sat:solution-callback', currentBestScore: 5, elapsedSeconds: 0.002, solutionIndex: 1, commentCount: 0 }],
      ['job.state_changed', { state: 'completed', terminal: true }],
    ] as const;
    return route.fulfill({
      status: 200,
      headers: { ...CORS_HEADERS, 'Content-Type': 'text/event-stream' },
      body: events.map(([name, data]) => `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`).join(''),
    });
  }
  if (pathname === `/optimize/${JOB_ID}/xlsx`) {
    return route.fulfill({
      status: 200,
      headers: {
        ...CORS_HEADERS,
        'Content-Disposition': `attachment; filename="${WORKBOOK_NAME}"`,
        'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      },
      body: await createMockXlsxBuffer(),
    });
  }
  return route.fulfill({ status: 404, headers: CORS_HEADERS });
}

test.beforeEach(async ({ page }) => {
  await page.clock.setFixedTime(FIXED_TIME);
  await page.addInitScript(css => {
    document.addEventListener('DOMContentLoaded', () => {
      const style = document.createElement('style');
      style.textContent = css;
      document.head.append(style);
    });
  }, CAPTURE_CSS);
  // Keep every request local. The release check sees the current version, so no banner appears.
  await page.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (url.origin === SITE_ORIGIN) {
      const file = exportedFile(url.pathname);
      return file ? route.fulfill({ path: file }) : route.fulfill({ status: 404, path: path.join(EXPORT_DIR, '404.html') });
    }
    if (url.hostname === 'api.github.com') {
      return fulfillJson(route, url.pathname.endsWith('/tags') ? [{ name: APP_VERSION }] : []);
    }
    if (BACKEND_URL.test(url.href)) return mockBackend(route, url.pathname);
    return route.abort();
  });
});

async function upload(page: Page, text: string, name = 'schedule.yaml') {
  await page.goto('/save-and-load');
  await page.locator('input[type="file"]').setInputFiles({ name, mimeType: 'application/yaml', buffer: Buffer.from(text) });
  await expect(page.getByRole('status', { name: 'YAML import summary' })).toBeVisible();
}

async function createEmptySchedule(page: Page) {
  await page.goto('/');
  await page.getByRole('button', { name: 'New Schedule', exact: true }).click();
  await page.getByRole('button', { name: 'Create empty schedule' }).click();
  await expect(page.getByRole('heading', { name: 'Confirm Reset' })).toBeHidden();
}

async function openDateRangeForm(page: Page, startDate: string, endDate: string) {
  await page.goto('/dates');
  await page.getByRole('button', { name: 'Set Date Range' }).click();
  await page.locator('#startDate').fill(startDate);
  await page.locator('#endDate').fill(endDate);
  await page.locator('#endDate').blur();
}

// The nearest rounded card around a heading. Card header rows are not rounded.
const ROUNDED_ANCESTOR = 'xpath=ancestor::*[self::div or self::section][contains(@class, "rounded")][1]';

function card(page: Page, heading: string): Locator {
  return page.getByRole('heading', { name: heading, exact: true }).first().locator(ROUNDED_ANCESTOR);
}

// The form labels are not linked to their inputs, so take the input that follows the label.
function field(page: Page, label: string): Locator {
  return page.locator('label', { hasText: label })
    .locator('xpath=following-sibling::*[1]/descendant-or-self::input').first();
}

// The page's own content, without the surrounding margin and fixed tab arrows.
function content(page: Page): Locator {
  return page.locator('main > div').first();
}

async function capture(target: Page | Locator, file: string) {
  const style = 'goto' in target ? undefined : HIDE_TAB_ARROWS;
  await target.screenshot({ path: file, animations: 'disabled', caret: 'hide', style });
}

// Health checks time real requests. Show one fixed latency for both hosted servers so reruns produce identical images.
async function pinServerLatency(page: Page) {
  await page.waitForFunction(() => {
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let count = 0;
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      if (/^ · \d+ ms$/.test(node.textContent ?? '')) {
        node.textContent = ' · 24 ms';
        count += 1;
      }
    }
    return count === 2;
  });
}

// Crop a tall element to its top part.
async function captureTop(page: Page, target: Locator, file: string, height: number) {
  await target.scrollIntoViewIfNeeded();
  await page.evaluate(() => window.scrollTo(0, 0));
  const box = await target.boundingBox();
  if (!box) throw new Error(`${file} has no visible target.`);
  await page.screenshot({
    path: file, animations: 'disabled', caret: 'hide', fullPage: true, style: HIDE_TAB_ARROWS,
    clip: { x: box.x, y: box.y, width: box.width, height: Math.min(height, box.height) },
  });
}

test.describe('Quick Start', () => {
  test.use({ viewport: { width: 960, height: 1024 } });

  test('home page', async ({ page }) => {
    await page.setViewportSize({ width: 1920, height: 1080 });
    await page.goto('/');
    await expect(page.getByRole('button', { name: 'Continue' })).toBeVisible();
    await capture(page, path.join(IMAGES, '00-home.png'));
  });

  test('empty schedule confirmation', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('button', { name: 'New Schedule', exact: true }).click();
    const dialog = page.getByRole('heading', { name: 'Confirm Reset' }).locator('xpath=..');
    await capture(dialog, path.join(IMAGES, '01-start-new.png'));
  });

  test('date range form', async ({ page }) => {
    await createEmptySchedule(page);
    await openDateRangeForm(page, '2026-08-01', '2026-08-07');
    await capture(card(page, 'Set Date Range'), path.join(IMAGES, '02-date-range.png'));
  });

  test('schedule pages', async ({ page }) => {
    await upload(page, QUICK_START_YAML);
    await page.goto('/shift-types');
    await capture(content(page), path.join(IMAGES, '03-shift-types.png'));
    await page.goto('/shift-type-requirements');
    await capture(content(page), path.join(IMAGES, '04-staffing-requirement.png'));
    await page.setViewportSize({ width: 1536, height: 1024 });
    await page.goto('/shift-requests');
    await capture(card(page, 'Shift Preference Matrix'), path.join(IMAGES, '05-shift-request.png'));
    await page.setViewportSize({ width: 960, height: 1024 });
    await page.goto('/save-and-load');
    await captureTop(page, content(page), path.join(IMAGES, '06-save-and-load.png'), 560);
  });

  test('optimize and result', async ({ page }) => {
    await upload(page, QUICK_START_YAML);
    await page.goto('/optimize-and-export');
    const optimize = page.getByRole('button', { name: 'Optimize and Download', exact: true });
    await expect(optimize).toBeEnabled();
    await pinServerLatency(page);
    await capture(card(page, 'Setup and Run'), path.join(IMAGES, '07-optimize.png'));
    await optimize.click();
    await expect(page.getByText('Schedule optimized and downloaded successfully!')).toBeVisible();
    await capture(card(page, 'Live Result'), path.join(IMAGES, '08-result.png'));
  });
});

test.describe('page guides', () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  const pages: [string, string][] = [
    ['/dates', '10-real-dates.png'],
    ['/people', '11-real-people.png'],
    ['/shift-types', '12-real-shift-types.png'],
    ['/shift-type-requirements', '13-real-requirements.png'],
    ['/shift-requests', '14-real-requests.png'],
    ['/shift-type-successions', '15-real-successions.png'],
    ['/shift-counts', '16-real-counts.png'],
    ['/shift-affinities', '17-real-affinities.png'],
    ['/export-layout', '18-real-export-layout.png'],
    ['/save-and-load', '19-real-save-load.png'],
    ['/optimize-and-export', '20-real-optimize.png'],
    ['/experimental-ai', '21-real-experimental-ai.png'],
  ];

  test('example schedule pages', async ({ page }) => {
    await upload(page, EXAMPLE_YAML, EXAMPLE_NAME);
    for (const [route, file] of pages) {
      await page.goto(route);
      await expect(page.locator('main h1, main h2').first()).toBeVisible();
      if (route === '/optimize-and-export') {
        await expect(page.getByRole('button', { name: 'Optimize and Download', exact: true })).toBeEnabled();
        await pinServerLatency(page);
      }
      if (route === '/experimental-ai') await expect(page.getByText(/^online$/i)).toBeVisible();
      // The AI page follows the end of the conversation. Show every page from its top.
      await page.evaluate(() => window.scrollTo(0, 0));
      await capture(page, path.join(IMAGES, file));
    }
  });
});

test.describe('Build a Real Schedule', () => {
  test.use({ viewport: { width: 1500, height: 1000 } });

  test('date range', async ({ page }) => {
    // The calendar opens on the current month, so show the month that the guide schedules.
    await page.clock.setFixedTime(new Date('2025-11-01T08:00:00Z'));
    await createEmptySchedule(page);
    await openDateRangeForm(page, '2025-11-01', '2025-11-30');
    await capture(page, path.join(BUILD_REAL, 'build-real-dates-range.png'));
  });

  test('uploaded people', async ({ page }) => {
    await upload(page, exampleBeforePeopleGroups());
    await page.goto('/people');
    await capture(page, path.join(BUILD_REAL, 'build-real-people.png'));
  });

  test('import notice', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await upload(page, EXAMPLE_YAML, EXAMPLE_NAME);
    await capture(page.getByRole('status', { name: 'YAML import summary' }), path.join(BUILD_REAL, 'yaml-import-summary.png'));
  });

  test('example lists', async ({ page }) => {
    await upload(page, EXAMPLE_YAML, EXAMPLE_NAME);
    await page.goto('/dates');
    await capture(card(page, 'Dates Groups'), path.join(BUILD_REAL, 'build-real-date-groups.png'));
    await page.goto('/people');
    await capture(card(page, 'People Groups'), path.join(BUILD_REAL, 'build-real-people-groups.png'));
    await page.goto('/shift-types');
    await capture(page, path.join(BUILD_REAL, 'build-real-shift-types.png'));
    await page.goto('/shift-type-requirements');
    await capture(card(page, 'Current Requirements'), path.join(BUILD_REAL, 'build-real-requirements.png'));
    const coverageWarning = page.getByText('Requirement coverage warnings', { exact: true }).locator(ROUNDED_ANCESTOR);
    await capture(coverageWarning, path.join(BUILD_REAL, 'build-real-coverage-warning.png'));
    await page.goto('/shift-requests');
    await captureTop(page, card(page, 'Current People History'), path.join(BUILD_REAL, 'build-real-history.png'), 900);
    await captureTop(page, card(page, 'Shift Preference Matrix'), path.join(BUILD_REAL, 'build-real-requests.png'), 900);
    await page.goto('/shift-type-successions');
    await capture(card(page, 'Current Successions'), path.join(BUILD_REAL, 'build-real-successions.png'));
    await page.goto('/shift-counts');
    await capture(card(page, 'Current Shift Counts'), path.join(BUILD_REAL, 'build-real-counts.png'));
    await page.goto('/save-and-load');
    await captureTop(page, card(page, 'Current State YAML'), path.join(BUILD_REAL, 'build-real-final-yaml.png'), 410);
  });

  test('requirement form', async ({ page }) => {
    await upload(page, EXAMPLE_YAML, EXAMPLE_NAME);
    await page.goto('/shift-type-requirements');
    await page.getByRole('button', { name: 'Add Requirement' }).click();
    await page.getByRole('radio', { name: 'N', exact: true }).check();
    await field(page, 'Required Number of People').fill('12');
    await field(page, 'Preferred Number of People').fill('13');
    await page.getByRole('checkbox', { name: 'All Nurses w/o Students', exact: true }).check();
    await page.getByRole('checkbox', { name: 'ALL', exact: true }).last().check();
    await field(page, 'Weight (priority)').fill('-1000000000000');
    await capture(card(page, 'Add New Requirement'), path.join(BUILD_REAL, 'build-real-requirement-form.png'));
  });

  test('succession form', async ({ page }) => {
    await upload(page, EXAMPLE_YAML, EXAMPLE_NAME);
    await page.goto('/shift-type-successions');
    await page.getByRole('button', { name: 'Add Succession' }).click();
    await page.getByPlaceholder('e.g., Forbid Evening -> Day succession').fill('Forbid');
    await page.getByRole('checkbox', { name: 'ALL', exact: true }).first().check();
    await page.getByRole('button', { name: 'Evening', exact: true }).click();
    await page.getByRole('button', { name: 'Day', exact: true }).click();
    await page.getByRole('checkbox', { name: 'ALL', exact: true }).last().check();
    await page.getByRole('button', { name: '-∞', exact: true }).click();
    await capture(card(page, 'Add New Succession'), path.join(BUILD_REAL, 'build-real-succession-form.png'));
  });
});
