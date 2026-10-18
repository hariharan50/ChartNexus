/**
 * Stock Watch's own persisted state: the journal, the alert rules, the
 * watchlist and the cost schedule.
 *
 * **This is browser storage, not an account.** Entries live in `localStorage`
 * on this device, in this browser. They are not synced, not backed up, and —
 * critically — they are *not* broker fills. Every surface that renders them
 * says so. A journal that looks like a statement is worse than no journal:
 * somebody eventually reconciles their taxes against it.
 *
 * A server-backed journal is the obvious next step and would need a migration,
 * a context and an API; this is deliberately the version that does not pretend
 * to be that. The shapes below are the ones such an API would take, so moving
 * them later is a transport change rather than a redesign.
 *
 * Writes are guarded: a private window, a browser with site data blocked, or a
 * full quota all throw on `setItem`, and losing a journal entry must not take
 * the page down with it.
 */

import { create } from 'zustand';
import type { OptionType } from './calc/black-scholes';
import { type CostRates, NO_COSTS } from './calc/plan';

const KEY = 'cn-stock-watch-v1';

export interface JournalEntry {
  id: string;
  /** ISO instant the entry was written. */
  recordedAt: string;
  /** ISO date of the trade. */
  tradeDate: string;
  symbol: string;
  type: OptionType;
  strike: number;
  expiry: string;
  lotSize: number;
  lots: number;
  entry: number;
  exit?: number | undefined;
  stop?: number | undefined;
  target?: number | undefined;
  /** The reader's own name for the setup, e.g. "ORB long". */
  setup: string;
  rationale: string;
  exitReason: string;
  /** Context captured at entry, so the trade can be reviewed against it. */
  context: {
    spot?: number | undefined;
    futuresBasisPercent?: number | undefined;
    atmIv?: number | undefined;
    pcrOi?: number | undefined;
    structure?: string | undefined;
  };
  grossPnl?: number | undefined;
  charges?: number | undefined;
  netPnl?: number | undefined;
  /** Rules the trader broke, their own list. */
  violations: string[];
  notes: string;
}

export type AlertKind =
  | 'price_above'
  | 'price_below'
  | 'breakout_above'
  | 'breakdown_below'
  | 'relative_volume_above'
  | 'oi_change_above'
  | 'futures_buildup'
  | 'iv_above'
  | 'iv_below'
  | 'spread_above'
  | 'feed_stale'
  | 'ban_status';

export interface AlertRule {
  id: string;
  symbol: string;
  kind: AlertKind;
  /** The level, percentage or ratio the rule compares against. */
  threshold: number;
  enabled: boolean;
  /** Epoch ms of the last time this rule fired, for the cooldown. */
  lastFiredAt?: number | undefined;
  note?: string | undefined;
}

export interface FiredAlert {
  ruleId: string;
  symbol: string;
  kind: AlertKind;
  message: string;
  /** The observed value that crossed the threshold. */
  observed: number;
  threshold: number;
  at: number;
}

interface Persisted {
  journal: JournalEntry[];
  alerts: AlertRule[];
  watchlist: string[];
  costs: CostRates;
}

interface StockWatchState extends Persisted {
  hydrated: boolean;
  init: () => void;
  addJournalEntry: (entry: Omit<JournalEntry, 'id' | 'recordedAt'>) => void;
  removeJournalEntry: (id: string) => void;
  addAlert: (rule: Omit<AlertRule, 'id'>) => void;
  toggleAlert: (id: string) => void;
  removeAlert: (id: string) => void;
  markFired: (id: string, at: number) => void;
  toggleWatch: (symbol: string) => void;
  setCosts: (costs: CostRates) => void;
}

const EMPTY: Persisted = { journal: [], alerts: [], watchlist: [], costs: NO_COSTS };

function read(): Persisted {
  if (typeof window === 'undefined') return EMPTY;
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return EMPTY;
    const parsed = JSON.parse(raw) as Partial<Persisted>;
    return {
      journal: Array.isArray(parsed.journal) ? parsed.journal : [],
      alerts: Array.isArray(parsed.alerts) ? parsed.alerts : [],
      watchlist: Array.isArray(parsed.watchlist) ? parsed.watchlist : [],
      costs: { ...NO_COSTS, ...(parsed.costs ?? {}) }
    };
  } catch {
    // A payload from an older shape, or storage the browser refuses to read.
    // Starting empty loses the journal; throwing loses the page. The page wins.
    return EMPTY;
  }
}

function write(state: Persisted): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(KEY, JSON.stringify(state));
  } catch {
    // Private window, blocked site data, or a full quota. Nothing to do and
    // nothing worth interrupting the reader over — the in-memory state is
    // still correct for this session.
  }
}

/** Collision-resistant enough for rows a single person types. */
function id(): string {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

export const useStockWatchStore = create<StockWatchState>()((set, get) => {
  const persist = () => {
    const { journal, alerts, watchlist, costs } = get();
    write({ journal, alerts, watchlist, costs });
  };

  return {
    ...EMPTY,
    hydrated: false,

    // Called from an effect, never from render: this reads `localStorage`,
    // which does not exist during SSR, and a store mutated during render is a
    // cross-request leak on the server singleton.
    init: () => {
      if (get().hydrated) return;
      set({ ...read(), hydrated: true });
    },

    addJournalEntry: (entry) => {
      set((state) => ({
        journal: [{ ...entry, id: id(), recordedAt: new Date().toISOString() }, ...state.journal]
      }));
      persist();
    },

    removeJournalEntry: (entryId) => {
      set((state) => ({ journal: state.journal.filter((row) => row.id !== entryId) }));
      persist();
    },

    addAlert: (rule) => {
      set((state) => ({ alerts: [...state.alerts, { ...rule, id: id() }] }));
      persist();
    },

    toggleAlert: (ruleId) => {
      set((state) => ({
        alerts: state.alerts.map((rule) =>
          rule.id === ruleId ? { ...rule, enabled: !rule.enabled } : rule
        )
      }));
      persist();
    },

    removeAlert: (ruleId) => {
      set((state) => ({ alerts: state.alerts.filter((rule) => rule.id !== ruleId) }));
      persist();
    },

    markFired: (ruleId, at) => {
      set((state) => ({
        alerts: state.alerts.map((rule) =>
          rule.id === ruleId ? { ...rule, lastFiredAt: at } : rule
        )
      }));
      persist();
    },

    toggleWatch: (symbol) => {
      set((state) => ({
        watchlist: state.watchlist.includes(symbol)
          ? state.watchlist.filter((entry) => entry !== symbol)
          : [...state.watchlist, symbol]
      }));
      persist();
    },

    setCosts: (costs) => {
      set({ costs });
      persist();
    }
  };
});

/**
 * How long a rule stays quiet after firing.
 *
 * Without it, a price alert on a level the stock is sitting on fires on every
 * poll — fifteen seconds apart, forever — and the reader turns alerts off
 * entirely, which costs them the one that mattered.
 */
export const ALERT_COOLDOWN_MS = 5 * 60_000;

export interface AlertContext {
  symbol: string;
  price?: number | undefined;
  dayHigh?: number | undefined;
  dayLow?: number | undefined;
  relativeVolume?: number | undefined;
  /** Largest absolute per-strike OI change on the chain, as a percentage. */
  maxOiChangePercent?: number | undefined;
  futuresBuildup?: string | undefined;
  atmIv?: number | undefined;
  /** Widest spread percentage among the strikes near the money. */
  worstSpreadPercent?: number | undefined;
  feedStale?: boolean | undefined;
  banned?: boolean | undefined;
}

/**
 * Evaluate the enabled rules for this symbol against what is on screen.
 *
 * Pure: it returns what fired and leaves recording the cooldown to the caller,
 * so the same function can be unit-tested without a store or a clock.
 */
export function evaluateAlerts(
  rules: AlertRule[],
  context: AlertContext,
  now: number
): FiredAlert[] {
  const fired: FiredAlert[] = [];

  for (const rule of rules) {
    if (!rule.enabled || rule.symbol !== context.symbol) continue;
    if (rule.lastFiredAt != null && now - rule.lastFiredAt < ALERT_COOLDOWN_MS) continue;

    const hit = (
      observed: number | undefined,
      test: (value: number) => boolean,
      message: string
    ) => {
      if (observed == null || !Number.isFinite(observed) || !test(observed)) return;
      fired.push({
        ruleId: rule.id,
        symbol: rule.symbol,
        kind: rule.kind,
        message,
        observed,
        threshold: rule.threshold,
        at: now
      });
    };

    switch (rule.kind) {
      case 'price_above':
        hit(context.price, (v) => v >= rule.threshold, `Price crossed above ${rule.threshold}.`);
        break;
      case 'price_below':
        hit(context.price, (v) => v <= rule.threshold, `Price crossed below ${rule.threshold}.`);
        break;
      case 'breakout_above':
        hit(context.price, (v) => v > rule.threshold, `Broke out above ${rule.threshold}.`);
        break;
      case 'breakdown_below':
        hit(context.price, (v) => v < rule.threshold, `Broke down below ${rule.threshold}.`);
        break;
      case 'relative_volume_above':
        hit(
          context.relativeVolume,
          (v) => v >= rule.threshold,
          `Relative volume reached ${context.relativeVolume?.toFixed(2)}×.`
        );
        break;
      case 'oi_change_above':
        hit(
          context.maxOiChangePercent,
          (v) => Math.abs(v) >= rule.threshold,
          `A strike's open interest moved ${context.maxOiChangePercent?.toFixed(1)}%.`
        );
        break;
      case 'iv_above':
        hit(
          context.atmIv,
          (v) => v >= rule.threshold,
          `ATM IV reached ${context.atmIv?.toFixed(1)}%.`
        );
        break;
      case 'iv_below':
        hit(
          context.atmIv,
          (v) => v <= rule.threshold,
          `ATM IV fell to ${context.atmIv?.toFixed(1)}%.`
        );
        break;
      case 'spread_above':
        hit(
          context.worstSpreadPercent,
          (v) => v >= rule.threshold,
          `Spread near the money widened to ${context.worstSpreadPercent?.toFixed(1)}% of mid.`
        );
        break;
      case 'futures_buildup':
        if (context.futuresBuildup && context.futuresBuildup !== 'neutral') {
          fired.push({
            ruleId: rule.id,
            symbol: rule.symbol,
            kind: rule.kind,
            message: `Futures classified as ${context.futuresBuildup.replace(/_/g, ' ')}.`,
            observed: 1,
            threshold: rule.threshold,
            at: now
          });
        }
        break;
      case 'feed_stale':
        if (context.feedStale) {
          fired.push({
            ruleId: rule.id,
            symbol: rule.symbol,
            kind: rule.kind,
            message: 'Market data went stale while the market is open.',
            observed: 1,
            threshold: rule.threshold,
            at: now
          });
        }
        break;
      case 'ban_status':
        if (context.banned != null) {
          // Only fires on a *change* the caller has detected; the context flag
          // is the current state and the caller decides whether it moved.
          fired.push({
            ruleId: rule.id,
            symbol: rule.symbol,
            kind: rule.kind,
            message: context.banned ? 'Now in the F&O ban period.' : 'No longer in the ban period.',
            observed: context.banned ? 1 : 0,
            threshold: rule.threshold,
            at: now
          });
        }
        break;
    }
  }

  return fired;
}

export const ALERT_LABELS: Record<AlertKind, string> = {
  price_above: 'Price above',
  price_below: 'Price below',
  breakout_above: 'Breakout above',
  breakdown_below: 'Breakdown below',
  relative_volume_above: 'Relative volume above',
  oi_change_above: 'Strike OI change above (%)',
  futures_buildup: 'Futures build-up detected',
  iv_above: 'ATM IV above (%)',
  iv_below: 'ATM IV below (%)',
  spread_above: 'Spread above (% of mid)',
  feed_stale: 'Market data went stale',
  ban_status: 'F&O ban status'
};
