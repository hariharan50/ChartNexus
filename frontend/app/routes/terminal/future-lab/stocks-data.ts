import type { BuildupState, FuturesRow } from '$contexts/futures-analytics/types';

/** Formatting, labelling and derivation for the Live Future Market Movers board. */

// -- build-up states --------------------------------------------------------

/**
 * The five states, in the order the legend reads them: the two that add open
 * interest, then the two that remove it, then the refusal to call it.
 *
 * `abbr` is what the Build cell shows — a dense board has room for two letters,
 * not "Short Covering" — and `tone` drives the cell tint.
 */
export interface StateMeta {
  id: BuildupState;
  label: string;
  abbr: string;
  arrow: string;
  tone: 'strong-up' | 'up' | 'strong-down' | 'down' | 'flat';
}

export const STATES: StateMeta[] = [
  { id: 'long_buildup', label: 'Long', abbr: 'L', arrow: '↗', tone: 'strong-up' },
  { id: 'short_covering', label: 'Short Covering', abbr: 'SC', arrow: '↑', tone: 'up' },
  { id: 'short_buildup', label: 'Short', abbr: 'S', arrow: '↘', tone: 'strong-down' },
  { id: 'long_unwinding', label: 'Long Unwinding', abbr: 'LU', arrow: '↓', tone: 'down' },
  { id: 'neutral', label: 'Neutral', abbr: '—', arrow: '', tone: 'flat' }
];

const BY_ID = new Map(STATES.map((entry) => [entry.id, entry]));

export function stateMeta(state: BuildupState): StateMeta {
  return BY_ID.get(state) ?? STATES[STATES.length - 1]!;
}

/** Counts per state, in legend order. Zero-count states are kept so the row
 *  does not reflow as the market moves. */
export function countByState(rows: FuturesRow[]): { meta: StateMeta; count: number }[] {
  const tally = new Map<BuildupState, number>();
  for (const row of rows) tally.set(row.state, (tally.get(row.state) ?? 0) + 1);
  return STATES.map((meta) => ({ meta, count: tally.get(meta.id) ?? 0 }));
}

// -- numbers ----------------------------------------------------------------

const price = new Intl.NumberFormat('en-IN', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2
});

export function fmtPrice(value: string | number | null): string {
  const n = toNumber(value);
  return n === null ? '—' : price.format(n);
}

/**
 * Lakh and crore, the way an Indian terminal reads large counts.
 *
 * `2.4 Cr` is legible at a glance where `24,000,000` is not, and this is a
 * board of two hundred such numbers.
 */
export function fmtCompact(value: number | null): string {
  if (value === null || value === undefined) return '—';
  const abs = Math.abs(value);
  if (abs >= 1e7) return `${(value / 1e7).toFixed(2)} Cr`;
  if (abs >= 1e5) return `${(value / 1e5).toFixed(1)} L`;
  if (abs >= 1e3) return `${(value / 1e3).toFixed(1)} K`;
  return String(value);
}

/**
 * A signed percentage, or an em dash.
 *
 * The dash carries weight: the API returns null when a figure could not be
 * measured — most often Vol %, which no live broker payload supplies — and
 * printing "0.00%" there would assert something nobody observed.
 */
export function fmtPercent(value: string | number | null): string {
  const n = toNumber(value);
  if (n === null) return '—';
  return `${n >= 0 ? '+' : ''}${n.toFixed(2)}%`;
}

export function toNumber(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined || value === '') return null;
  const n = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(n) ? n : null;
}

/** 'up' | 'down' | null — null when there is nothing to colour. */
export function direction(value: string | number | null): 'up' | 'down' | null {
  const n = toNumber(value);
  if (n === null || n === 0) return null;
  return n > 0 ? 'up' : 'down';
}

// -- grouping ---------------------------------------------------------------

/** Sectors present, alphabetical. Rows with no sector are skipped, not
 *  bucketed under "Unknown" — index contracts legitimately have none. */
export function sectorsIn(rows: FuturesRow[]): string[] {
  const seen = new Set<string>();
  for (const row of rows) if (row.sector) seen.add(row.sector);
  return [...seen].sort((a, b) => a.localeCompare(b));
}

export interface SectorPerformance {
  sector: string;
  changePercent: number;
  count: number;
}

/**
 * Mean price move per sector, strongest first.
 *
 * An unweighted mean on purpose: this answers "how is the sector trading",
 * where a small name moving 6% is as informative as a large one moving 1%. A
 * cap-weighted average would need market caps we do not hold.
 */
export function sectorPerformance(rows: FuturesRow[]): SectorPerformance[] {
  const totals = new Map<string, { sum: number; count: number }>();
  for (const row of rows) {
    const change = toNumber(row.price_change_percent);
    if (!row.sector || change === null) continue;
    const entry = totals.get(row.sector) ?? { sum: 0, count: 0 };
    entry.sum += change;
    entry.count += 1;
    totals.set(row.sector, entry);
  }
  return [...totals.entries()]
    .map(([sector, { sum, count }]) => ({ sector, changePercent: sum / count, count }))
    .sort((a, b) => b.changePercent - a.changePercent);
}

export interface AdvanceDecline {
  label: string;
  advances: number;
  declines: number;
}

/** Advancing vs declining counts for a set of rows. Unchanged contracts are in
 *  neither column — the pair is a ratio of conviction, not a partition. */
export function advanceDecline(label: string, rows: FuturesRow[]): AdvanceDecline {
  let advances = 0;
  let declines = 0;
  for (const row of rows) {
    const tone = direction(row.price_change_percent);
    if (tone === 'up') advances += 1;
    else if (tone === 'down') declines += 1;
  }
  return { label, advances, declines };
}

// -- export -----------------------------------------------------------------

const CSV_HEADERS = [
  'Symbol',
  'Company',
  'Sector',
  'Open HL',
  'Price',
  'Price %',
  'OI',
  'OI %',
  'Build-up',
  'Volume',
  'Vol %'
] as const;

/** The rows as they are on screen, filters and sort included. */
export function boardCsv(rows: FuturesRow[]): string {
  const lines = [CSV_HEADERS.join(',')];
  for (const row of rows) {
    lines.push(
      [
        row.symbol,
        quote(row.name ?? ''),
        row.sector ?? '',
        row.open_marker ?? '',
        row.price,
        row.price_change_percent ?? '',
        row.open_interest,
        row.oi_change_percent ?? '',
        stateMeta(row.state).label,
        row.volume ?? '',
        row.volume_change_percent ?? ''
      ].join(',')
    );
  }
  return lines.join('\n');
}

/** Company names contain commas; nothing else in the row does. */
function quote(value: string): string {
  return value.includes(',') ? `"${value.replace(/"/g, '""')}"` : value;
}

/** `fno-stocks-2026-09-21-1540.csv` — sortable, and says when it was taken. */
export function csvFilename(prefix = 'fno-board', now = new Date()): string {
  const at = (unit: Intl.DateTimeFormatPartTypes) =>
    new Intl.DateTimeFormat('en-GB', {
      timeZone: 'Asia/Kolkata',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false
    })
      .formatToParts(now)
      .find((part) => part.type === unit)?.value ?? '';
  return `${prefix}-${at('year')}-${at('month')}-${at('day')}-${at('hour')}${at('minute')}.csv`;
}
