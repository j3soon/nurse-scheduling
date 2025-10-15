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

export function getWeightWithPositivePrefix(weight: number | string, add_commas: boolean = true): string {
  if (weight === null) {
    console.error(`Weight is null. ${ERROR_SHOULD_NOT_HAPPEN}`);
    return "Error (dev)";
  }
  if (typeof weight === 'string') return "Error";
  const weight_str = add_commas ? weight.toLocaleString() : weight.toString();
  if (typeof weight === 'number' && weight > 0) return `+${weight_str}`;
  return weight_str;
}

export function getWeightDisplayLabel(weight: number | string): string {
  if (weight === Infinity) return '+∞';
  if (weight === -Infinity) return '-∞';
  // Reduce weights length
  const ret = getWeightWithPositivePrefix(weight, false);
  if (typeof weight === 'number') {
    const units = [
      { value: 1e12, symbol: 't' },
      { value: 1e9, symbol: 'b' },
      { value: 1e6, symbol: 'm' },
      { value: 1e3, symbol: 'k' },
    ];

    for (const { value, symbol } of units) {
      if (weight % value === 0) return ret.slice(0, -String(value).length + 1) + symbol;
      if (weight % (value / 10) === 0)
        return ret.slice(0, -String(value).length + 1) + '.' + ret.slice(-String(value).length + 1, -String(value).length + 2) + symbol;
    }
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
