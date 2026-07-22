/** Display helpers. Every number in the UI goes through one of these. */

export const PILLAR_LABEL: Record<string, string> = {
  P2_chronic: 'Chronic burden',
  P2_acute: 'Acute burden',
  P3_access: 'Access & supply',
  P4_afford: 'Affordability',
  P5_mom_chronic: 'Chronic momentum',
  P5_mom_acute: 'Acute momentum',
  P5_mom_adoption: 'Care-adoption momentum',
};

export const PILLAR_ORDER = [
  'P2_chronic', 'P2_acute', 'P3_access', 'P4_afford',
  'P5_mom_chronic', 'P5_mom_acute', 'P5_mom_adoption',
] as const;

export const TIER_LABEL: Record<string, string> = {
  A: 'Band A — top quartile',
  B: 'Band B',
  C: 'Band C',
  D: 'Band D — bottom quartile',
};

export function num(v: number | null | undefined, dp = 2): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  return v.toFixed(dp);
}

export function int(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  return Math.round(v).toLocaleString('en-IN');
}

export function pct(v: number | null | undefined, dp = 1): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  return `${v.toFixed(dp)}%`;
}

export function signed(v: number | null | undefined, dp = 2): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  return `${v >= 0 ? '+' : ''}${v.toFixed(dp)}`;
}

/** Compact Indian population: 12,34,567 -> 12.3L, 1,23,45,678 -> 1.23Cr */
export function popShort(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return '—';
  if (v >= 1e7) return `${(v / 1e7).toFixed(2)} Cr`;
  if (v >= 1e5) return `${(v / 1e5).toFixed(1)} L`;
  return int(v);
}

export function shortDate(iso: string | undefined | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso);
  return d.toISOString().slice(0, 10);
}

/** CSV with the quoting rules that survive Excel. */
export function toCsv(rows: Record<string, unknown>[], columns?: string[]): string {
  if (!rows.length) return '';
  const cols = columns ?? Object.keys(rows[0]);
  const esc = (v: unknown) => {
    if (v === null || v === undefined) return '';
    const s = String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  return [cols.join(','), ...rows.map((r) => cols.map((c) => esc(r[c])).join(','))].join(
    '\n',
  );
}

export function downloadCsv(filename: string, csv: string): void {
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
