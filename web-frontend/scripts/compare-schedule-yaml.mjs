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

import { readFileSync } from 'node:fs';
import yaml from 'js-yaml';

const [expectedPath, actualPath] = process.argv.slice(2);
if (!expectedPath || !actualPath) {
  console.error('Usage: bun scripts/compare-schedule-yaml.mjs EXPECTED.yaml ACTUAL.yaml');
  process.exit(2);
}

function normalize(value, path = '') {
  if (typeof value === 'number' && !Number.isFinite(value)) {
    return String(value);
  }
  if (Array.isArray(value)) {
    const entries = value.map(entry => normalize(entry, path));
    return path === 'preferences'
      ? entries.sort((left, right) => JSON.stringify(left).localeCompare(JSON.stringify(right)))
      : entries;
  }
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value)
        .filter(([key]) => !(path === '' && key === 'appVersion'))
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([key, entry]) => [key, normalize(entry, path ? `${path}.${key}` : key)]),
    );
  }
  return value;
}

function differences(expected, actual, path = 'schedule', found = []) {
  if (found.length >= 10) return found;
  if (JSON.stringify(expected) === JSON.stringify(actual)) return found;
  if (Array.isArray(expected) && Array.isArray(actual)) {
    if (expected.length !== actual.length) found.push(`${path}: expected ${expected.length} entries, got ${actual.length}`);
    for (let index = 0; index < Math.min(expected.length, actual.length); index++) {
      differences(expected[index], actual[index], `${path}[${index}]`, found);
      if (found.length >= 10) break;
    }
  } else if (expected && actual && typeof expected === 'object' && typeof actual === 'object') {
    for (const key of new Set([...Object.keys(expected), ...Object.keys(actual)])) {
      differences(expected[key], actual[key], `${path}.${key}`, found);
      if (found.length >= 10) break;
    }
  } else {
    found.push(`${path}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
  return found;
}

try {
  const expected = normalize(yaml.load(readFileSync(expectedPath, 'utf8')));
  const actual = normalize(yaml.load(readFileSync(actualPath, 'utf8')));
  const mismatches = differences(expected, actual);
  if (mismatches.length) {
    console.error(`Schedule YAML differs:\n${mismatches.join('\n')}`);
    process.exitCode = 1;
  } else {
    console.log('Schedule YAML values match (ignoring appVersion and preference order).');
  }
} catch (error) {
  console.error(`Could not compare schedule YAML: ${error.message}`);
  process.exitCode = 2;
}
