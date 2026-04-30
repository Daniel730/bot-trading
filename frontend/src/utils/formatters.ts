export function formatCurrency(value: number | null | undefined) {
  if (value === null || value === undefined) return '—';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(value);
}

export function formatPercent(value: number | null | undefined, scale = 100) {
  if (value === null || value === undefined) return '—';
  return `${(value * scale).toFixed(scale === 100 ? 1 : 0)}%`;
}

export function formatCompact(value: number | null | undefined, suffix = '') {
  if (value === null || value === undefined) return '—';
  return `${value.toFixed(1)}${suffix}`;
}

export function formatDateTime(value?: string | null) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

export function getTrendClass(value: number | null | undefined) {
  if (value === null || value === undefined) return '';
  if (value > 0) return 'positive';
  if (value < 0) return 'negative';
  return '';
}

export function sparklinePath(values: number[], width: number, height: number) {
  if (!values.length) return '';
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  return values
    .map((value, index) => {
      const x = (index / Math.max(values.length - 1, 1)) * width;
      const y = height - ((value - min) / range) * height;
      return `${index === 0 ? 'M' : 'L'} ${x} ${y}`;
    })
    .join(' ');
}
