import assert from 'node:assert/strict';
import test from 'node:test';

import {
  chromiumHostResolverRules,
  createNetworkPolicy,
  isImplicitLoopbackHost,
  normalizeAllowedHost,
  redactUrlCredentials,
} from './network-policy.mjs';

const addresses = new Map([
  ['docs.example', ['203.0.113.10', '2001:db8::10']],
  ['localhost', ['127.0.0.1', '::1']],
  ['metadata.example', ['169.254.169.254']],
]);
const resolver = async hostname => addresses.get(hostname) ?? [hostname];

test('redacts URL userinfo from arbitrary text', () => {
  assert.equal(
    redactUrlCredentials("failed at https://alice:p'ass@example.com/path"),
    'failed at https://example.com/path',
  );
  assert.equal(
    redactUrlCredentials('failed at https://alice:p"ass@example.com/path'),
    'failed at https://example.com/path',
  );
});

test('normalizes exact allowed hosts and rejects ports', () => {
  assert.equal(normalizeAllowedHost('DOCS.EXAMPLE.'), 'docs.example');
  assert.throws(() => normalizeAllowedHost('docs.example:80'), /without a scheme, port, or path/u);
});

test('recognizes only literal loopback and localhost as implicit hosts', () => {
  assert.equal(isImplicitLoopbackHost('localhost'), true);
  assert.equal(isImplicitLoopbackHost('127.0.0.1'), true);
  assert.equal(isImplicitLoopbackHost('docs.example'), false);
});

test('remote captures require explicit access to loopback', async () => {
  const policy = createNetworkPolicy(['docs.example'], { allowImplicitLoopback: false, resolver });
  await policy.assertAllowed('https://docs.example/');
  await assert.rejects(policy.assertAllowed('http://localhost/'), /network host is not allowed/u);
  await assert.rejects(policy.assertAllowed('http://127.0.0.1/'), /network host is not allowed/u);
});

test('local captures allow loopback but not remote hosts', async () => {
  const policy = createNetworkPolicy([], { allowImplicitLoopback: true, resolver });
  await policy.assertAllowed('http://localhost/');
  await policy.assertAllowed('http://127.0.0.2/');
  await assert.rejects(policy.assertAllowed('https://docs.example/'), /network host is not allowed/u);
});

test('link-local DNS results remain blocked when the host is explicit', async () => {
  const policy = createNetworkPolicy(['metadata.example'], { allowImplicitLoopback: false, resolver });
  await assert.rejects(policy.assertAllowed('https://metadata.example/'), /link-local network host is not allowed/u);
});

test('pins approved hostname resolution for Chromium', async () => {
  const policy = createNetworkPolicy(['docs.example'], { allowImplicitLoopback: false, resolver });
  const pins = await policy.pinnedHostnames();
  assert.deepEqual(pins, [{ hostname: 'docs.example', address: '203.0.113.10' }]);
  assert.equal(chromiumHostResolverRules(pins), 'MAP docs.example 203.0.113.10');
});
