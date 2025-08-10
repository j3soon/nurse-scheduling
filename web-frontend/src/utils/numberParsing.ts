import { ERROR_SHOULD_NOT_HAPPEN } from "@/constants/errors";

// Shared utility functions for parsing number values that can include infinity
export function parseWeightValue(inputValue: string): number | string {
  // Handle special string values
  const inputValueLower = inputValue.toLowerCase();
  if (inputValueLower === 'infinity' || inputValueLower === 'inf' || inputValueLower === '∞') {
    return Infinity;
  } else if (inputValueLower === '-infinity' || inputValueLower === '-inf' || inputValueLower === '-∞') {
    return -Infinity;
  } else {
    const parsed = parseInt(inputValue);
    if (isNaN(parsed)) {
      // Invalid values are left as strings
      return inputValue;
    }
    return parsed;
  }
}

export function parseNumberValue(inputValue: string): number | string {
  const parsed = parseInt(inputValue);
  if (isNaN(parsed)) {
    // Invalid values are left as strings
    return inputValue;
  }
  return parsed;
}

export function getWeightWithPositivePrefix(weight: number | string): string {
  if (weight === null) {
    console.error(`Weight is null. ${ERROR_SHOULD_NOT_HAPPEN}`);
    return "Error (dev)";
  }
  if (typeof weight === 'string') return "Error";
  if (typeof weight === 'number' && weight > 0) return `+${weight.toLocaleString()}`;
  return weight.toLocaleString();
}

export function getWeightDisplayLabel(weight: number | string): string {
  if (weight === Infinity) return '+∞';
  if (weight === -Infinity) return '-∞';
  // Reduce weights length
  const ret = getWeightWithPositivePrefix(weight);
  if (typeof weight === 'number') {
    const str = weight.toString();
    if (str.endsWith('000000000')) return ret.slice(0, -9) + 'b';
    if (str.endsWith('000000')) return ret.slice(0, -6) + 'm';
    if (str.endsWith('000')) return ret.slice(0, -3) + 'k';
  }
  return ret;
}

export function getWeightColor(weight: number | string): string {
  const numWeight = typeof weight === 'string' ? 0 : weight;
  if (numWeight > 0) return 'text-green-600 bg-green-50';
  if (numWeight < 0) return 'text-red-600 bg-red-50';
  if (typeof weight === 'string') return 'text-orange-800 bg-orange-300';
  return 'text-gray-500 bg-gray-50';
}

export function isValidWeightValue(value: number | string): boolean {
  if (typeof value === 'string') {
    // String values are invalid (parsing failed)
    return false;
  }
  if (typeof value === 'number') {
    // Allow finite numbers and positive/negative infinity
    return isFinite(value) || value === Infinity || value === -Infinity;
  }
  return false;
}

export function isValidNumberValue(value: number | string): boolean {
  if (typeof value === 'string') {
    // String values are invalid (parsing failed)
    return false;
  }
  return typeof value === 'number' && isFinite(value);
}
