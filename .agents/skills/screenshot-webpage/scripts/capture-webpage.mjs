#!/usr/bin/env node

import { existsSync, mkdirSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, extname, resolve } from 'node:path';

function fail(message) {
  console.error(`error: ${message}`);
  process.exit(2);
}

function usage() {
  console.log(`Usage:
  capture-webpage.mjs URL OUTPUT.png [options]

Options:
  --module-root PATH       Directory whose node_modules contains playwright
  --executable-path PATH   Browser executable outside Playwright's cache
  --storage-state PATH     Playwright state with cookies and local storage
  --viewport WIDTHxHEIGHT  Default: 1440x900
  --device-scale NUMBER    Default: 1
  --color-scheme light|dark
  --ready SELECTOR         Wait for a selector before capture
  --expect-text TEXT       Repeat to require visible page text
  --selector SELECTOR      Capture one visible element
  --full-page              Capture the complete document
  --hide SELECTOR          Repeat to hide an element before capture
  --mask SELECTOR          Repeat to mask matching elements
  --wait-ms NUMBER         Extra settling time, maximum 30000
  --force                  Replace an existing output file
  --help`);
}

function parseArguments(argv) {
  const positional = [];
  const options = {
    moduleRoot: process.cwd(),
    executablePath: undefined,
    storageState: undefined,
    viewport: '1440x900',
    deviceScale: 1,
    colorScheme: 'light',
    ready: undefined,
    expectTexts: [],
    selector: undefined,
    fullPage: false,
    hideSelectors: [],
    maskSelectors: [],
    waitMs: 0,
    force: false,
  };
  const valueOptions = new Map([
    ['--module-root', 'moduleRoot'],
    ['--executable-path', 'executablePath'],
    ['--storage-state', 'storageState'],
    ['--viewport', 'viewport'],
    ['--device-scale', 'deviceScale'],
    ['--color-scheme', 'colorScheme'],
    ['--ready', 'ready'],
    ['--selector', 'selector'],
    ['--wait-ms', 'waitMs'],
  ]);

  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (argument === '--help') {
      usage();
      process.exit(0);
    }
    if (argument === '--force' || argument === '--full-page') {
      options[argument === '--force' ? 'force' : 'fullPage'] = true;
      continue;
    }
    if (argument === '--expect-text' || argument === '--hide' || argument === '--mask') {
      const value = argv[index + 1];
      if (value === undefined) fail(`${argument} requires a value`);
      const key = argument === '--expect-text' ? 'expectTexts' : argument === '--hide' ? 'hideSelectors' : 'maskSelectors';
      options[key].push(value);
      index += 1;
      continue;
    }
    if (valueOptions.has(argument)) {
      const value = argv[index + 1];
      if (value === undefined) fail(`${argument} requires a value`);
      options[valueOptions.get(argument)] = value;
      index += 1;
      continue;
    }
    if (argument.startsWith('--')) fail(`unknown option ${argument}`);
    positional.push(argument);
  }

  if (positional.length !== 2) {
    usage();
    fail('provide one URL and one output PNG');
  }
  if (options.selector && options.fullPage) fail('--selector and --full-page cannot be combined');
  const viewportMatch = /^(\d+)x(\d+)$/.exec(String(options.viewport));
  if (!viewportMatch) fail('--viewport must use WIDTHxHEIGHT');
  const width = Number.parseInt(viewportMatch[1], 10);
  const height = Number.parseInt(viewportMatch[2], 10);
  if (width < 240 || width > 7680 || height < 240 || height > 7680) fail('viewport dimensions must be between 240 and 7680');
  options.viewport = { width, height };
  options.deviceScale = Number.parseFloat(String(options.deviceScale));
  if (!Number.isFinite(options.deviceScale) || options.deviceScale < 1 || options.deviceScale > 3) fail('--device-scale must be between 1 and 3');
  options.waitMs = Number.parseInt(String(options.waitMs), 10);
  if (!Number.isInteger(options.waitMs) || options.waitMs < 0 || options.waitMs > 30000) fail('--wait-ms must be between 0 and 30000');
  if (!['light', 'dark'].includes(String(options.colorScheme))) fail('--color-scheme must be light or dark');
  return { url: positional[0], output: resolve(positional[1]), options };
}

function loadPlaywright(moduleRoot) {
  try {
    const requireFromRoot = createRequire(resolve(moduleRoot, 'package.json'));
    return requireFromRoot(requireFromRoot.resolve('playwright'));
  } catch {
    fail(`cannot load playwright from ${moduleRoot}; choose a --module-root containing that dependency`);
  }
}

const { url, output, options } = parseArguments(process.argv.slice(2));
let parsedUrl;
try {
  parsedUrl = new URL(url);
} catch {
  fail(`invalid URL: ${url}`);
}
if (!['http:', 'https:'].includes(parsedUrl.protocol)) fail('URL must use HTTP or HTTPS');
if (extname(output).toLowerCase() !== '.png') fail('output must use the .png extension');
if (existsSync(output) && !options.force) fail(`output exists: ${output}; pass --force to replace it`);
if (options.executablePath && !existsSync(resolve(options.executablePath))) fail(`browser executable does not exist: ${options.executablePath}`);
if (options.storageState && !existsSync(resolve(options.storageState))) fail(`storage state does not exist: ${options.storageState}`);

const { chromium } = loadPlaywright(resolve(options.moduleRoot));
const browser = await chromium.launch({
  headless: true,
  ...(options.executablePath ? { executablePath: resolve(options.executablePath) } : {}),
});
let finalUrl;
let title;
let captureError;
try {
  const context = await browser.newContext({
    viewport: options.viewport,
    deviceScaleFactor: options.deviceScale,
    colorScheme: options.colorScheme,
    ...(options.storageState ? { storageState: resolve(options.storageState) } : {}),
  });
  const page = await context.newPage();
  const response = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 });
  if (response && !response.ok()) throw new Error(`page returned HTTP ${response.status()}: ${response.url()}`);
  if (options.ready) await page.locator(options.ready).first().waitFor({ state: 'visible', timeout: 15000 });
  for (const text of options.expectTexts) {
    await page.getByText(text, { exact: false }).filter({ visible: true }).first().waitFor({ state: 'visible', timeout: 15000 });
  }
  if (options.waitMs) await page.waitForTimeout(options.waitMs);
  for (const selector of options.hideSelectors) {
    await page.locator(selector).evaluateAll(elements => {
      for (const element of elements) element.style.setProperty('visibility', 'hidden', 'important');
    });
  }
  const mask = options.maskSelectors.map(selector => page.locator(selector));
  const screenshotOptions = {
    path: output,
    animations: 'disabled',
    caret: 'hide',
    mask,
    scale: 'css',
    style: '*, *::before, *::after { animation: none !important; transition: none !important; }',
  };
  mkdirSync(dirname(output), { recursive: true });
  if (options.selector) {
    const target = page.locator(options.selector).first();
    await target.waitFor({ state: 'visible', timeout: 15000 });
    await target.screenshot(screenshotOptions);
  } else {
    await page.screenshot({ ...screenshotOptions, fullPage: options.fullPage });
  }
  finalUrl = page.url();
  title = await page.title();
  await context.close();
} catch (error) {
  captureError = error;
} finally {
  await browser.close();
}
if (captureError) fail(captureError instanceof Error ? captureError.message : String(captureError));

console.log(JSON.stringify({
  url,
  finalUrl,
  title,
  output,
  viewport: options.viewport,
  capture: options.selector ? 'element' : options.fullPage ? 'full-page' : 'viewport',
  assertions: options.expectTexts.length,
  storageState: options.storageState ? resolve(options.storageState) : null,
}));
