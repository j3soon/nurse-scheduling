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

// Utility functions for YAML generation with custom formatting
import yaml from 'js-yaml';

// Type definitions for CustomDump class
export interface CustomDumpOptions {
  flowLevel?: number;
  indent?: number;
  lineWidth?: number;
  noRefs?: boolean;
  [key: string]: unknown;
}

// Custom function to detect leaf arrays (arrays containing only primitives)
export const isLeafArray = (value: unknown): boolean => {
  if (!Array.isArray(value)) return false;
  return value.every(item =>
    typeof item === 'string' ||
    typeof item === 'number' ||
    typeof item === 'boolean' ||
    item === null ||
    item === undefined
  );
};

// Custom dump wrapper for flow style
export class CustomDump {
  data: unknown;
  opts: CustomDumpOptions;

  constructor(data: unknown, opts: CustomDumpOptions = {}) {
    this.data = data;
    this.opts = opts;
  }

  represent(): string {
    let result = yaml.dump(this.data, Object.assign({ replacer, schema, noCompatMode: true }, this.opts));
    result = result.trim();
    if (result.includes('\n')) result = '\n' + result;
    return result;
  }
}

// Custom YAML type for flow formatting
export const CustomDumpType = new yaml.Type('!format', {
  kind: 'scalar',
  resolve: () => false,
  instanceOf: CustomDump,
  represent: (data: object) => {
    if (data instanceof CustomDump) {
      return data.represent();
    }
    return String(data);
  }
});

// Custom schema with the flow type
export const schema = yaml.DEFAULT_SCHEMA.extend({ implicit: [CustomDumpType] });

// Replacer function to detect leaf arrays and apply flow style
export function replacer(key: string, value: unknown) {
  if (key === '') return value; // top-level, don't change this
  if (isLeafArray(value)) {
    return new CustomDump(value, { flowLevel: 0 });
  }
  if (value instanceof Date) {
    return value.toISOString().split('T')[0];
  }
  return value; // default
}

/**
 * Generate YAML string from a state object with custom flow style for leaf arrays
 * Ref: https://github.com/nodeca/js-yaml/issues/586#issuecomment-814310104
 *
 * @param stateObject - The state object to convert to YAML
 * @param options - Optional CustomDumpOptions for controlling YAML output
 * @returns YAML string with custom formatting
 */
export function generateYamlFromState(
  stateObject: unknown,
  options: CustomDumpOptions = {}
): string {
  const defaultOptions: CustomDumpOptions = {
    indent: 2,
    lineWidth: 120,
    noRefs: true,
    ...options
  };

  return new CustomDump(stateObject, defaultOptions).represent().trim() + '\n';
}

