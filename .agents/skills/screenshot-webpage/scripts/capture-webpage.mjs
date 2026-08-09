#!/usr/bin/env node

import { existsSync, mkdirSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, extname, resolve } from 'node:path';

import {
  chromiumHostResolverRules,
  createNetworkPolicy,
  isImplicitLoopbackHost,
  normalizeAllowedHost,
  redactUrlCredentials,
} from './network-policy.mjs';

function fail(message) {
  console.error(`error: ${redactUrlCredentials(message)}`);
  process.exit(2);
}

function usage() {
  console.log(`Usage:
  capture-webpage.mjs URL OUTPUT.png [options]

Options:
  --module-root PATH       Directory whose node_modules contains playwright
  --executable-path PATH   Browser executable outside Playwright's cache
  --storage-state PATH     Playwright state with cookies and local storage
  --allow-host HOST        Repeat to authorize an exact remote hostname
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
    allowHosts: [],
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
    if (argument === '--expect-text' || argument === '--hide' || argument === '--mask' || argument === '--allow-host') {
      const value = argv[index + 1];
      if (value === undefined) fail(`${argument} requires a value`);
      const key = argument === '--expect-text'
        ? 'expectTexts'
        : argument === '--hide'
          ? 'hideSelectors'
          : argument === '--mask'
            ? 'maskSelectors'
            : 'allowHosts';
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
  try {
    options.allowHosts = options.allowHosts.map(normalizeAllowedHost);
  } catch (error) {
    fail(error instanceof Error ? error.message : String(error));
  }
  return { url: positional[0], output: resolve(positional[1]), options };
}

function versionAtLeast(version, minimumMajor, minimumMinor) {
  const match = /^(\d+)\.(\d+)/u.exec(String(version));
  if (!match) return false;
  const major = Number.parseInt(match[1], 10);
  const minor = Number.parseInt(match[2], 10);
  return major > minimumMajor || (major === minimumMajor && minor >= minimumMinor);
}

function loadPlaywright(moduleRoot) {
  try {
    const requireFromRoot = createRequire(resolve(moduleRoot, 'package.json'));
    const version = requireFromRoot('playwright/package.json').version;
    if (!versionAtLeast(version, 1, 51)) fail(`playwright 1.51 or newer is required; found ${version}`);
    return requireFromRoot(requireFromRoot.resolve('playwright'));
  } catch {
    fail(`cannot load playwright from ${moduleRoot}; choose a --module-root containing that dependency`);
  }
}

const { url: rawUrl, output, options } = parseArguments(process.argv.slice(2));
let parsedUrl;
try {
  parsedUrl = new URL(rawUrl);
} catch {
  fail('invalid URL');
}
if (!['http:', 'https:'].includes(parsedUrl.protocol)) fail('URL must use HTTP or HTTPS');
if (parsedUrl.username || parsedUrl.password) fail('URL credentials are not allowed');
parsedUrl.username = '';
parsedUrl.password = '';
const url = parsedUrl.href;
if (extname(output).toLowerCase() !== '.png') fail('output must use the .png extension');
if (existsSync(output) && !options.force) fail(`output exists: ${output}; pass --force to replace it`);
if (options.executablePath && !existsSync(resolve(options.executablePath))) fail(`browser executable does not exist: ${options.executablePath}`);
if (options.storageState && !existsSync(resolve(options.storageState))) fail(`storage state does not exist: ${options.storageState}`);

const networkPolicy = createNetworkPolicy(options.allowHosts, {
  allowImplicitLoopback: isImplicitLoopbackHost(parsedUrl.hostname),
});
try {
  await networkPolicy.assertAllowed(url);
} catch (error) {
  fail(error instanceof Error ? error.message : String(error));
}
let hostResolverRules;
try {
  hostResolverRules = chromiumHostResolverRules(await networkPolicy.pinnedHostnames());
} catch (error) {
  fail(error instanceof Error ? error.message : String(error));
}

const { chromium } = loadPlaywright(resolve(options.moduleRoot));
const browser = await chromium.launch({
  headless: true,
  ...(hostResolverRules ? { args: [`--host-resolver-rules=${hostResolverRules}`] } : {}),
  ...(options.executablePath ? { executablePath: resolve(options.executablePath) } : {}),
});
let finalUrl;
let title;
let captureError;
let context;
try {
  context = await browser.newContext({
    viewport: options.viewport,
    deviceScaleFactor: options.deviceScale,
    colorScheme: options.colorScheme,
    serviceWorkers: 'block',
    ...(options.storageState ? { storageState: resolve(options.storageState) } : {}),
  });
  let rejectPolicyViolation;
  let policyViolated = false;
  const policyViolation = new Promise((_, reject) => {
    rejectPolicyViolation = reject;
  });
  const recordPolicyViolation = error => {
    if (policyViolated) return;
    policyViolated = true;
    rejectPolicyViolation(error);
  };
  const pagePolicies = new WeakMap();
  const installPagePolicy = page => {
    if (!pagePolicies.has(page)) {
      pagePolicies.set(page, (async () => {
        const cdp = await context.newCDPSession(page);
        cdp.on('Fetch.requestPaused', event => {
          void (async () => {
            try {
              await networkPolicy.assertAllowed(event.request.url);
            } catch (error) {
              recordPolicyViolation(error);
              await cdp.send('Fetch.failRequest', {
                requestId: event.requestId,
                errorReason: 'BlockedByClient',
              }).catch(() => {});
              return;
            }
            await cdp.send('Fetch.continueRequest', { requestId: event.requestId }).catch(() => {});
          })();
        });
        await cdp.send('Fetch.enable', { patterns: [
          { urlPattern: 'http://*', requestStage: 'Request' },
          { urlPattern: 'https://*', requestStage: 'Request' },
        ] });
      })());
    }
    return pagePolicies.get(page);
  };
  await context.route('**/*', async route => {
    try {
      await networkPolicy.assertAllowed(route.request().url());
      await installPagePolicy(route.request().frame().page());
    } catch (error) {
      recordPolicyViolation(error);
      await route.abort('blockedbyclient').catch(() => {});
      return;
    }
    await route.continue();
  });
  await context.routeWebSocket(/.*/u, async webSocket => {
    try {
      await networkPolicy.assertAllowed(webSocket.url(), ['ws:', 'wss:']);
    } catch (error) {
      recordPolicyViolation(error);
      await webSocket.close({ code: 1008, reason: 'Network target is not allowed' }).catch(() => {});
      return;
    }
    webSocket.connectToServer();
  });
  const page = await context.newPage();
  await installPagePolicy(page);

  await Promise.race([(async () => {
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
  })(), policyViolation]);
} catch (error) {
  captureError = error;
} finally {
  if (context) await context.close().catch(() => {});
  await browser.close();
}
if (captureError) fail(captureError instanceof Error ? captureError.message : String(captureError));

console.log(JSON.stringify({
  url,
  finalUrl: redactUrlCredentials(finalUrl),
  title: redactUrlCredentials(title),
  output,
  viewport: options.viewport,
  capture: options.selector ? 'element' : options.fullPage ? 'full-page' : 'viewport',
  assertions: options.expectTexts.length,
  storageState: options.storageState ? resolve(options.storageState) : null,
}));
