import { lookup } from 'node:dns/promises';
import { BlockList, isIP } from 'node:net';

const loopbackAddresses = new BlockList();
loopbackAddresses.addSubnet('127.0.0.0', 8, 'ipv4');
loopbackAddresses.addAddress('::1', 'ipv6');
loopbackAddresses.addSubnet('::ffff:7f00:0', 104, 'ipv6');

const linkLocalAddresses = new BlockList();
linkLocalAddresses.addSubnet('169.254.0.0', 16, 'ipv4');
linkLocalAddresses.addSubnet('fe80::', 10, 'ipv6');
linkLocalAddresses.addSubnet('::ffff:a9fe:0', 112, 'ipv6');

export function redactUrlCredentials(value) {
  return String(value).replace(/\b((?:https?|wss?):\/\/)[^\s/?#<>]*@/giu, '$1');
}

export function normalizeHostname(hostname) {
  let normalized = String(hostname).toLowerCase();
  if (normalized.startsWith('[') && normalized.endsWith(']')) normalized = normalized.slice(1, -1);
  if (normalized.endsWith('.')) normalized = normalized.slice(0, -1);
  return normalized;
}

export function normalizeAllowedHost(value) {
  const candidate = String(value).trim();
  const bracketedIpv6 = candidate.startsWith('[') && candidate.endsWith(']');
  if (!candidate || /[\s/@?#]/u.test(candidate) || (!bracketedIpv6 && candidate.includes(':'))) {
    throw new Error('--allow-host requires a hostname without a scheme, port, or path');
  }
  let parsed;
  try {
    parsed = new URL(`http://${candidate}`);
  } catch {
    throw new Error('--allow-host requires a valid hostname');
  }
  if (parsed.port || parsed.username || parsed.password || parsed.pathname !== '/') {
    throw new Error('--allow-host requires a hostname without a scheme, port, or path');
  }
  return normalizeHostname(parsed.hostname);
}

function addressFamily(address) {
  return isIP(address) === 4 ? 'ipv4' : 'ipv6';
}

function isLoopbackAddress(address) {
  const family = isIP(address);
  return family !== 0 && loopbackAddresses.check(address, addressFamily(address));
}

function isLinkLocalAddress(address) {
  const family = isIP(address);
  return family !== 0 && linkLocalAddresses.check(address, addressFamily(address));
}

export function isImplicitLoopbackHost(hostname) {
  const normalized = normalizeHostname(hostname);
  return normalized === 'localhost' || isLoopbackAddress(normalized);
}

async function resolveAddresses(hostname) {
  if (isIP(hostname)) return [hostname];
  try {
    return (await lookup(hostname, { all: true, verbatim: true })).map(result => result.address);
  } catch {
    throw new Error(`cannot resolve network host: ${hostname}`);
  }
}

export function createNetworkPolicy(allowHosts, { allowImplicitLoopback = false, resolver = resolveAddresses } = {}) {
  const explicitlyAllowed = new Set(allowHosts);
  const hostnameChecks = new Map();

  async function checkHostname(hostname) {
    const normalized = normalizeHostname(hostname);
    if (!hostnameChecks.has(normalized)) {
      hostnameChecks.set(normalized, (async () => {
        const implicitLoopback = allowImplicitLoopback && isImplicitLoopbackHost(normalized);
        if (!explicitlyAllowed.has(normalized) && !implicitLoopback) {
          throw new Error(`network host is not allowed: ${normalized}`);
        }
        const addresses = await resolver(normalized);
        if (!addresses.length || addresses.some(address => isIP(address) === 0)) {
          throw new Error(`cannot resolve network host: ${normalized}`);
        }
        if (addresses.some(isLinkLocalAddress)) throw new Error(`link-local network host is not allowed: ${normalized}`);
        if (!explicitlyAllowed.has(normalized) && addresses.some(address => !isLoopbackAddress(address))) {
          throw new Error(`network host does not resolve only to loopback addresses: ${normalized}`);
        }
        return addresses;
      })());
    }
    return hostnameChecks.get(normalized);
  }

  return {
    async assertAllowed(value, protocols = ['http:', 'https:']) {
      let parsed;
      try {
        parsed = new URL(value);
      } catch {
        throw new Error('invalid network URL');
      }
      if (!protocols.includes(parsed.protocol)) throw new Error(`network URL must use ${protocols.join(' or ')}`);
      if (parsed.username || parsed.password) throw new Error('URL credentials are not allowed');
      await checkHostname(parsed.hostname);
    },

    async pinnedHostnames() {
      const hostnames = new Set(explicitlyAllowed);
      if (allowImplicitLoopback) hostnames.add('localhost');
      const pins = [];
      for (const hostname of hostnames) {
        if (isIP(hostname)) continue;
        const addresses = await checkHostname(hostname);
        const address = addresses.find(candidate => isIP(candidate) === 4) ?? addresses[0];
        pins.push({ hostname, address });
      }
      return pins;
    },
  };
}

export function chromiumHostResolverRules(pins) {
  return pins.map(({ hostname, address }) => {
    const replacement = isIP(address) === 6 ? `[${address}]` : address;
    return `MAP ${hostname} ${replacement}`;
  }).join(', ');
}
