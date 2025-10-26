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

