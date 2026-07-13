import { describe, it, expect } from 'vitest';
import { formatCurrency, formatPercent, getTrendClass } from './formatters';

describe('formatCurrency', () => {
  it('renders an em dash for null/undefined', () => {
    expect(formatCurrency(null)).toBe('—');
    expect(formatCurrency(undefined)).toBe('—');
  });

  it('shows cents so sub-dollar P&L is not hidden as $0', () => {
    expect(formatCurrency(0.53)).toBe('$0.53');
    expect(formatCurrency(-0.07)).toBe('-$0.07');
    expect(formatCurrency(0)).toBe('$0.00');
  });

  it('keeps thousands separators for large balances', () => {
    expect(formatCurrency(984558.37)).toBe('$984,558.37');
  });
});

describe('formatPercent', () => {
  it('scales fractions to percent', () => {
    expect(formatPercent(0.25)).toBe('25.0%');
    expect(formatPercent(null)).toBe('—');
  });
});

describe('getTrendClass', () => {
  it('classifies sign', () => {
    expect(getTrendClass(1)).toBe('positive');
    expect(getTrendClass(-1)).toBe('negative');
    expect(getTrendClass(0)).toBe('');
    expect(getTrendClass(null)).toBe('');
  });
});
