import type { Insight } from '../generated/contracts';

export const fieldLabel = (name: string) => {
  const text = name.replaceAll('_', ' ').replace(/\bavg\b/gi, 'average').replace(/\bpct\b/gi, 'percentage').replace(/\bid\b/gi, 'ID');
  return text.charAt(0).toUpperCase() + text.slice(1);
};
export function entryValue(value: unknown, isDate = false): string {
  if (value == null) return 'Not provided';
  if (typeof value === 'number') return value.toLocaleString(undefined, { maximumFractionDigits: 20 });
  if (isDate && typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value)) {
    const [year, month, day] = value.split('-').map(Number);
    return new Date(year, month - 1, day).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
  }
  return String(value);
}

export function formatMetric(insight: Insight): string {
  const value = insight.data?.value;
  if (typeof value !== 'number' || !Number.isFinite(value)) return '—';
  if (insight.data.is_percent) return `${new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 }).format(value)}%`;
  if (insight.data.is_currency && typeof insight.data.currency === 'string' && /^[A-Z]{3}$/.test(insight.data.currency)) {
    return new Intl.NumberFormat(undefined, { style: 'currency', currency: insight.data.currency, notation: 'compact', maximumFractionDigits: 1 }).format(value);
  }
  return new Intl.NumberFormat(undefined, { notation: 'compact', maximumFractionDigits: 1 }).format(value);
}
export const count = (value: number | null | undefined) => value == null ? '—' : new Intl.NumberFormat().format(value);
export const date = (value: string) => new Date(value).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
