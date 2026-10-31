/**
 * Wire types and pure helpers for the Trade Buddy page.
 *
 * Mirrors `contexts/trade_buddy/api/schemas.py` field-for-field, in snake_case,
 * because that is what the API emits. The helpers below are the page's whole
 * decision layer and are kept pure so they can be unit-tested without a render.
 */

import { apiFetch } from '$shared/api/client';

/**
 * The instruments Trade Buddy offers, by canonical name.
 *
 * Canonical (`NIFTY`), never the broker string (`NSE:NIFTY50-INDEX`) — that
 * translation happens in the Fyers adapter, where the catalog lookup lives,
 * because `BANKNIFTY` is quoted as `NIFTYBANK` and is not derivable by
 * pattern. Indices only; the backend rejects anything else.
 */
export const WATCHABLE = ['NIFTY', 'BANKNIFTY', 'SENSEX'] as const;

export type Watchable = (typeof WATCHABLE)[number];

export const DEFAULT_SYMBOL: Watchable = 'NIFTY';

/**
 * The symbol to show, given whatever the terminal-wide picker is set to.
 *
 * `useSelectedInstrument` is shared with nineteen other pages and may well be
 * on a stock. Falling back beats showing an instrument this page cannot watch
 * and then reporting it as having no levels, which would read as a bug.
 */
export function watchableOr(symbol: string | undefined, fallback: Watchable): Watchable {
  const upper = (symbol ?? '').toUpperCase();
  return (WATCHABLE as readonly string[]).includes(upper) ? (upper as Watchable) : fallback;
}

/** Poll cadence. The watcher persists state on every tick; this is just the read. */
export const REFETCH_MS = 5_000;

/**
 * Seconds of silence, during market hours, after which the feed is suspect.
 *
 * Matches `CN_TRADE_BUDDY_STALE_AFTER_SECONDS` (default 90). Duplicated rather
 * than fetched because the page only needs it to *colour a badge* — the alert
 * that actually matters is sent by the backend watchdog, which owns the real
 * threshold. A page that disagreed by a few seconds would mislead nobody; a page
 * that showed nothing until the backend spoke would hide a dead feed.
 */
export const STALE_AFTER_SECONDS = 90;

export type LevelRole = 'support' | 'resistance';

export type LevelState = 'idle' | 'approaching' | 'touched' | 'break_pending' | 'broken';

export type AlertKind =
  'approaching' | 'touched' | 'break_confirmed' | 'wick_rejected' | 'reclaimed' | 'gapped_through';

export interface LevelPayload {
  label: string;
  price: number;
  role: LevelRole;
}

export interface LevelsResponse {
  symbol: string;
  levels: LevelPayload[];
  marked_on?: string | null;
}

export interface WatcherState {
  label: string;
  level_price: number;
  role: LevelRole;
  state: LevelState;
  break_pending: boolean;
  alerts_remaining: number;
}

export interface ResolvedBands {
  touch: number;
  approach: number;
  break_buffer: number;
  confirm_hold_seconds: number;
  /** `atr` when scaled to this instrument, `points` when it fell back. */
  source: BandSource;
  atr: number | null;
  note: string | null;
}

export type BandSource = 'atr' | 'points';

export interface WatchRow {
  symbol: Watchable;
  watched: boolean;
  market_open: boolean;
  last_price: number | null;
  last_tick_at: string | null;
  levels_marked: number;
  nearest_label: string | null;
  nearest_distance: number | null;
  attention: LevelState | null;
  band_source: BandSource;
  levels_stale?: boolean;
}

export interface WatchlistResponse {
  instruments: WatchRow[];
}

export interface EngineState {
  symbol: string;
  /** The session the levels were marked for, ISO date. */
  marked_on?: string | null;
  /** Levels exist but are from an earlier session — nothing is alerted on. */
  levels_stale?: boolean;
  /**
   * Optional on purpose. A backend older than this field answers 200 without
   * it, and typing it as required let the page reach through `undefined` and
   * crash the render. The server always sends it; the type describes what can
   * actually arrive during a deploy skew.
   */
  bands?: ResolvedBands;
  market_open: boolean;
  last_tick_at: string | null;
  last_price: number | null;
  whatsapp_used: number;
  whatsapp_limit: number;
  levels: WatcherState[];
}

export interface Overrides {
  touch: number | null;
  approach: number | null;
  break_buffer: number | null;
  confirm_hold_seconds: number | null;
  cooldown_minutes: number | null;
  daily_alert_cap: number | null;
}

export interface SettingsDefaults {
  touch_multiple: number;
  approach_multiple: number;
  break_multiple: number;
  atr_period: number;
  confirm_hold_seconds: number;
  cooldown_minutes: number;
  daily_alert_cap: number;
  fallback_touch: number;
  fallback_approach: number;
  fallback_break_buffer: number;
}

export interface Settings {
  symbol: string;
  bands: ResolvedBands;
  cooldown_minutes: number;
  daily_alert_cap: number;
  defaults: SettingsDefaults;
  overrides: Overrides;
}

export type AlertChannelName = 'telegram' | 'whatsapp';

export interface AlertChannelView {
  channel: AlertChannelName;
  /** A secret is stored, whether or not a chat is linked yet. */
  configured: boolean;
  /** A send can actually happen right now. */
  ready: boolean;
  verified: boolean;
  enabled: boolean;
  /** The bot's @username — what tells two bots apart. */
  label: string | null;
  target: string | null;
  masked_secret: string | null;
}

export interface ChannelsResponse {
  channels: AlertChannelView[];
}

export interface TestAlertResponse {
  delivered: boolean;
  kind: AlertKind;
  rendered: string;
}

// -- endpoints --------------------------------------------------------------

export function getLevels(symbol = DEFAULT_SYMBOL): Promise<LevelsResponse> {
  return apiFetch<LevelsResponse>({ url: '/trade-buddy/levels', params: { symbol } });
}

export function setLevels(symbol: string, levels: LevelPayload[]): Promise<LevelsResponse> {
  return apiFetch<LevelsResponse>({
    url: '/trade-buddy/levels',
    method: 'PUT',
    body: JSON.stringify({ symbol, levels })
  });
}

export function clearLevels(symbol = DEFAULT_SYMBOL): Promise<void> {
  return apiFetch<void>({
    url: '/trade-buddy/levels',
    method: 'DELETE',
    params: { symbol }
  });
}

export function getEngineState(symbol = DEFAULT_SYMBOL): Promise<EngineState> {
  return apiFetch<EngineState>({ url: '/trade-buddy/state', params: { symbol } });
}

export function getChannels(): Promise<ChannelsResponse> {
  return apiFetch<ChannelsResponse>({ url: '/trade-buddy/channels' });
}

export function connectTelegram(secret: string): Promise<AlertChannelView> {
  return apiFetch<AlertChannelView>({
    url: '/trade-buddy/channels/telegram',
    method: 'PUT',
    body: JSON.stringify({ secret })
  });
}

/** `target` null asks the server to detect the chat from recent activity. */
export function linkTelegramChat(target: string | null): Promise<AlertChannelView> {
  return apiFetch<AlertChannelView>({
    url: '/trade-buddy/channels/telegram/link',
    method: 'POST',
    body: JSON.stringify({ target })
  });
}

export function testChannel(): Promise<void> {
  return apiFetch<void>({ url: '/trade-buddy/channels/telegram/test', method: 'POST' });
}

export function setChannelEnabled(
  channel: AlertChannelName,
  enabled: boolean
): Promise<AlertChannelView> {
  return apiFetch<AlertChannelView>({
    url: `/trade-buddy/channels/${channel}`,
    method: 'PATCH',
    body: JSON.stringify({ enabled })
  });
}

export function disconnectChannel(channel: AlertChannelName): Promise<void> {
  return apiFetch<void>({ url: `/trade-buddy/channels/${channel}`, method: 'DELETE' });
}

/**
 * Which step of the connect flow a channel is on.
 *
 * Derived rather than stored: the three booleans already say it, and a
 * separate status field would be a fourth thing to keep in agreement.
 */
export type ChannelStep = 'disconnected' | 'needs-chat' | 'paused' | 'ready';

export function channelStep(channel: AlertChannelView | undefined): ChannelStep {
  if (!channel || !channel.configured) return 'disconnected';
  if (!channel.target || !channel.verified) return 'needs-chat';
  if (!channel.enabled) return 'paused';
  return 'ready';
}

export const CHANNEL_STEP_COPY: Record<ChannelStep, { label: string; detail: string }> = {
  disconnected: {
    label: 'Not connected',
    detail: 'Create a bot with @BotFather and paste its token below.'
  },
  'needs-chat': {
    label: 'Needs a chat',
    detail:
      'Send your bot any message, then link the chat. A welcome message is delivered to prove it works before the chat is saved.'
  },
  paused: {
    label: 'Paused',
    detail: 'Connected, but switched off. Alerts are computed and not delivered.'
  },
  ready: { label: 'Ready', detail: 'Alerts will arrive here during market hours.' }
};

export function getSettings(symbol: string): Promise<Settings> {
  return apiFetch<Settings>({ url: '/trade-buddy/settings', params: { symbol } });
}

export function setSettings(symbol: string, overrides: Overrides): Promise<Settings> {
  return apiFetch<Settings>({
    url: '/trade-buddy/settings',
    method: 'PUT',
    body: JSON.stringify({ symbol, overrides })
  });
}

export function getWatchlist(): Promise<WatchlistResponse> {
  return apiFetch<WatchlistResponse>({ url: '/trade-buddy/watchlist' });
}

export function fireTestAlert(symbol: string, kind: AlertKind): Promise<TestAlertResponse> {
  return apiFetch<TestAlertResponse>({
    url: '/trade-buddy/test-alert',
    method: 'POST',
    body: JSON.stringify({ symbol, kind })
  });
}

// -- the six rows -----------------------------------------------------------

/**
 * The morning's blank form: three resistances above, three supports below.
 *
 * Fixed labels and a fixed order, because the order *is* the meaning — R3 is
 * further from price than R1, and a form that let them be reordered would make
 * the ladder below unreadable.
 */
export const LEVEL_SLOTS: readonly { label: string; role: LevelRole }[] = [
  { label: 'R3', role: 'resistance' },
  { label: 'R2', role: 'resistance' },
  { label: 'R1', role: 'resistance' },
  { label: 'S1', role: 'support' },
  { label: 'S2', role: 'support' },
  { label: 'S3', role: 'support' }
];

/** A draft row: the price is a string because it is bound to a text input. */
export interface DraftLevel {
  label: string;
  role: LevelRole;
  price: string;
}

export function emptyDraft(): DraftLevel[] {
  return LEVEL_SLOTS.map((slot) => ({ ...slot, price: '' }));
}

/** Fill the fixed six slots from whatever the API returned, by label. */
export function draftFrom(levels: LevelPayload[]): DraftLevel[] {
  const byLabel = new Map(levels.map((level) => [level.label.toUpperCase(), level]));
  return LEVEL_SLOTS.map((slot) => {
    const saved = byLabel.get(slot.label);
    return {
      label: slot.label,
      role: saved?.role ?? slot.role,
      price: saved ? String(saved.price) : ''
    };
  });
}

/**
 * Rows that carry a usable price, as the API wants them.
 *
 * Blank rows are dropped rather than rejected: marking four levels and leaving
 * S3 empty is a normal morning, not an error.
 */
export function toPayload(draft: DraftLevel[]): LevelPayload[] {
  return draft
    .map((row) => ({ label: row.label, role: row.role, price: Number(row.price) }))
    .filter((row) => row.price > 0 && Number.isFinite(row.price));
}

/**
 * What is wrong with the draft, or `null` when it can be saved.
 *
 * Checked here rather than left to the API so the message arrives before the
 * round-trip, and so a typo cannot silently become a level price. The ordering
 * rule is the one worth enforcing: supports above resistances would invert the
 * ladder and make every alert read backwards.
 */
export function validateDraft(draft: DraftLevel[]): string | null {
  const filled = draft.filter((row) => row.price.trim() !== '');
  if (filled.length === 0) return 'Mark at least one level.';

  for (const row of filled) {
    const price = Number(row.price);
    if (!Number.isFinite(price) || price <= 0) {
      return `${row.label} needs a positive price.`;
    }
  }

  const resistances = toPayload(draft).filter((row) => row.role === 'resistance');
  const supports = toPayload(draft).filter((row) => row.role === 'support');
  if (resistances.length && supports.length) {
    const lowestResistance = Math.min(...resistances.map((r) => r.price));
    const highestSupport = Math.max(...supports.map((s) => s.price));
    if (highestSupport >= lowestResistance) {
      return `A support (${highestSupport}) sits at or above a resistance (${lowestResistance}).`;
    }
  }

  const prices = toPayload(draft).map((row) => row.price);
  if (new Set(prices).size !== prices.length) {
    return 'Two levels share the same price.';
  }
  return null;
}

// -- display ----------------------------------------------------------------

/** How a level's state is named and weighted in the UI. */
export interface StateLook {
  label: string;
  /** Status tone. Deliberately never the only encoding — the label always shows. */
  tone: 'neutral' | 'info' | 'warn' | 'alert';
  /** A glyph, so state survives greyscale, CVD and forced-colours. */
  glyph: string;
}

const STATE_LOOK: Record<LevelState, StateLook> = {
  idle: { label: 'Idle', tone: 'neutral', glyph: '·' },
  approaching: { label: 'Approaching', tone: 'warn', glyph: '›' },
  touched: { label: 'Touched', tone: 'info', glyph: '◆' },
  break_pending: { label: 'Confirming', tone: 'warn', glyph: '◇' },
  broken: { label: 'Broken', tone: 'alert', glyph: '✕' }
};

export function stateLook(state: LevelState): StateLook {
  return STATE_LOOK[state] ?? STATE_LOOK.idle;
}

/**
 * Whether a level has flipped from the role its label implies.
 *
 * `R1` acting as support is the single most useful thing this page can say, and
 * it is derivable: the label names the level, the role names what it is doing
 * now, and a mismatch is a confirmed break that has not been reclaimed.
 */
export function hasFlipped(level: WatcherState): boolean {
  const impliedRole: LevelRole = level.label.toUpperCase().startsWith('R')
    ? 'resistance'
    : 'support';
  return level.role !== impliedRole;
}

export function formatPrice(price: number): string {
  return price.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

/** `14:32:05`, in IST, which is the only timezone this product thinks in. */
export function formatTime(iso: string | null): string {
  if (!iso) return '—';
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return '—';
  return parsed.toLocaleTimeString('en-IN', {
    timeZone: 'Asia/Kolkata',
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  });
}

export function secondsSince(iso: string | null, now: number): number | null {
  if (!iso) return null;
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return null;
  return Math.max(0, Math.round((now - parsed.getTime()) / 1000));
}

/**
 * A band as "0.06 x ATR = 42.1 pts", or just the points when ATR is missing.
 *
 * Both halves, always. The multiple is what transfers between instruments and
 * the points are what you can actually feel on a chart; showing one without
 * the other makes the setting either abstract or unexplainable.
 */
export function describeBand(points: number, atr: number | null, fallback: number): string {
  // With an ATR, both halves: the multiple transfers between indices, the
  // points are what you can check against a candle.
  if (atr !== null && atr > 0) {
    return `${(points / atr).toFixed(3)} x ATR = ${points.toFixed(1)} pts`;
  }
  // Without one there is no multiple to show. Naming the default matches what
  // the three throttle rows say and gives the reader something to restore to;
  // repeating "unscaled" per field would be the panel header said four times.
  return `Default ${fallback} pts`;
}

/**
 * Why nothing is being alerted on, when levels are stale. Null when current.
 *
 * Ranked above the band warning wherever both could show: unscaled bands make
 * alerts the wrong size, stale levels stop them entirely, and the second is
 * the one that explains a silent phone.
 */
export function staleWarning(state: EngineState | undefined): string | null {
  if (!state?.levels_stale) return null;
  const when = state.marked_on ? `from ${state.marked_on}` : 'from an earlier session';
  return `These levels are ${when}, not today. No alerts will be sent for ${state.symbol} until you re-mark them.`;
}

/**
 * The reassuring half of the same fact: these levels are for this session.
 *
 * Worth saying out loud rather than leaving to the absence of a warning. The
 * question a trader has at 09:16 is "are today's levels loaded?", and
 * answering it by showing nothing requires them to trust that the warning
 * would have appeared — which is exactly the trust that a missed alert
 * destroys.
 */
export function markedNote(state: EngineState | undefined): string | null {
  if (!state || state.levels_stale) return null;
  if (!state.marked_on) return null;
  return `Marked for ${state.marked_on}`;
}

/** Why the bands are unscaled, when they are. Null when all is well. */
export function bandWarning(bands: ResolvedBands | undefined): string | null {
  if (!bands) return null;
  if (bands.note) return bands.note;
  if (bands.source === 'points') {
    return 'ATR unavailable — using point defaults, which are sized for NIFTY. Thresholds on other indices will be too tight.';
  }
  return null;
}

export const EMPTY_OVERRIDES: Overrides = {
  touch: null,
  approach: null,
  break_buffer: null,
  confirm_hold_seconds: null,
  cooldown_minutes: null,
  daily_alert_cap: null
};

/** A blank field means "use the scaled default", not zero. */
export function parseOverride(raw: string): number | null {
  const trimmed = raw.trim();
  if (trimmed === '') return null;
  const value = Number(trimmed);
  return Number.isFinite(value) ? value : null;
}

/** The inverse, for seeding the inputs. */
export function overrideText(value: number | null): string {
  return value === null ? '' : String(value);
}

/**
 * What is wrong with a draft override set, or null.
 *
 * Only the pair comparison is checkable here, and only when both are set:
 * against an ATR-scaled value the browser has no ATR to compare with, so the
 * API reports that case instead.
 */
export function validateOverrides(draft: Overrides): string | null {
  const positive: (keyof Overrides)[] = ['touch', 'approach', 'break_buffer'];
  for (const key of positive) {
    const value = draft[key];
    if (value !== null && value <= 0) return `${key.replace('_', ' ')} must be above zero.`;
  }
  if (draft.confirm_hold_seconds !== null && draft.confirm_hold_seconds < 0) {
    return 'Hold cannot be negative.';
  }
  if (draft.cooldown_minutes !== null && draft.cooldown_minutes < 0) {
    return 'Cooldown cannot be negative.';
  }
  if (draft.daily_alert_cap !== null && draft.daily_alert_cap < 1) {
    return 'The daily cap must be at least one.';
  }
  if (draft.touch !== null && draft.approach !== null && draft.touch > draft.approach) {
    return 'Touch must not exceed approach — price would register TOUCHED before APPROACHING.';
  }
  return null;
}

export type FeedVerdict = 'closed' | 'waiting' | 'live' | 'stale';

/**
 * The page's most important sentence, as one value.
 *
 * Silence from a dead watcher and silence from a quiet market look identical
 * from the outside — that is the premise the whole feature rests on — so the
 * page must distinguish them rather than show a timestamp and leave the reader
 * to work it out.
 */
export function feedVerdict(state: EngineState | undefined, now: number): FeedVerdict {
  if (!state) return 'waiting';
  if (!state.market_open) return 'closed';
  const silence = secondsSince(state.last_tick_at, now);
  if (silence === null) return 'waiting';
  return silence > STALE_AFTER_SECONDS ? 'stale' : 'live';
}

export const FEED_COPY: Record<FeedVerdict, { label: string; detail: string }> = {
  closed: {
    label: 'Market closed',
    detail: 'Watching resumes at 09:15 IST on the next trading day.'
  },
  waiting: {
    label: 'Awaiting first tick',
    detail: 'The watcher is up but no price has arrived yet.'
  },
  live: { label: 'Live', detail: 'Ticks are arriving and the levels are being compared.' },
  stale: {
    label: 'Feed stale',
    detail: 'Market hours, but no tick recently — the feed may be down.'
  }
};

/**
 * Positions for the ladder, as fractions from the top (0) to the bottom (1).
 *
 * A shared scale across the levels *and* the price marker, padded so the
 * outermost level is not flush against the edge. Returns `null` when there is
 * nothing to scale against, so the caller can omit the ladder rather than draw
 * a degenerate one.
 */
export function ladderScale(
  levels: readonly { level_price: number }[],
  price: number | null
): ((value: number) => number) | null {
  const values = levels.map((l) => l.level_price);
  if (price !== null) values.push(price);
  if (values.length < 2) return null;

  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min;
  if (span <= 0) return null;

  // 8% padding each end so the extremes sit inside the frame and their labels
  // have somewhere to go.
  const pad = 0.08;
  return (value: number) => {
    const fraction = (max - value) / span;
    return pad + fraction * (1 - pad * 2);
  };
}
