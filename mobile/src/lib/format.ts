import type { Analysis, Insight } from '../generated/contracts';

export function analysisSourceLabel(analysis: Pick<Analysis, 'filename' | 'metadata'>): string | null {
  const context = analysis.metadata?.upload_context as {
    source_files?: { name?: unknown }[]; files?: { name?: unknown }[];
    cleaning?: { source_filename?: unknown }; current_file_name?: unknown;
  } | undefined;
  function visibleFilename(value: unknown): string | null {
    if (typeof value !== 'string') return null;
    const name = value.trim().split(/[\\/]/).pop() ?? '';
    const identifier = '(?:[a-f0-9]{32}|[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12})';
    if (!name || new RegExp(`${identifier}.*\\.parquet$`, 'i').test(name)) return null;
    return name;
  }
  for (const sources of [context?.source_files, context?.files]) {
    if (!Array.isArray(sources)) continue;
    const names = sources.flatMap(source => {
      const name = visibleFilename(source?.name);
      return name ? [name] : [];
    });
    if (names.length) return names.join(', ');
  }
  return visibleFilename(context?.cleaning?.source_filename) ??
    visibleFilename(context?.current_file_name) ?? visibleFilename(analysis.filename);
}

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
  const unit = insight.data.unit === 'million' ? ' million' : '';
  if (insight.data.is_percent) return `${new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 }).format(value)}%`;
  if (insight.data.is_currency && typeof insight.data.currency === 'string' && /^[A-Z]{3}$/.test(insight.data.currency)) {
    return new Intl.NumberFormat(undefined, { style: 'currency', currency: insight.data.currency, notation: unit ? 'standard' : 'compact', maximumFractionDigits: 1 }).format(value) + unit;
  }
  return new Intl.NumberFormat(undefined, { notation: unit ? 'standard' : 'compact', maximumFractionDigits: 1 }).format(value) + unit;
}
export const count = (value: number | null | undefined) => value == null ? '—' : new Intl.NumberFormat().format(value);
export const date = (value: string) => new Date(value).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
