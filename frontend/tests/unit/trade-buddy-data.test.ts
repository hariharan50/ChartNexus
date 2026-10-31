import { describe, expect, it } from 'vitest';
import {
  draftFrom,
  emptyDraft,
  feedVerdict,
  hasFlipped,
  ladderScale,
  LEVEL_SLOTS,
  secondsSince,
  stateLook,
  toPayload,
  validateDraft,
  bandWarning,
  CHANNEL_STEP_COPY,
  channelStep,
  describeBand,
  markedNote,
  staleWarning,
  EMPTY_OVERRIDES,
  overrideText,
  parseOverride,
  validateOverrides,
  watchableOr,
  WATCHABLE,
  type EngineState,
  type ResolvedBands,
  type LevelPayload,
  type WatcherState
} from '../../app/routes/terminal/tools/trade-buddy/trade-buddy-data';

/**
 * The Trade Buddy page's decision layer.
 *
 * Everything the page *decides* lives in pure functions so it can be pinned
 * here rather than through a render. The one that matters most is
 * `feedVerdict`: it is the page's answer to "is this silence a quiet market or
 * a dead watcher", which is the distinction the whole feature rests on.
 */

const TICK = '2026-10-26T04:30:00Z'; // 10:00 IST
const NOW = Date.parse(TICK);

function level(over: Partial<WatcherState> = {}): WatcherState {
  return {
    label: 'R1',
    level_price: 24_700,
    role: 'resistance',
    state: 'idle',
    break_pending: false,
    alerts_remaining: 3,
    ...over
  };
}

const BANDS: ResolvedBands = {
  touch: 6,
  approach: 25,
  break_buffer: 12,
  confirm_hold_seconds: 20,
  source: 'atr',
  atr: 200,
  note: null
};

function engine(over: Partial<EngineState> = {}): EngineState {
  return {
    symbol: 'NIFTY',
    bands: BANDS,
    market_open: true,
    last_tick_at: TICK,
    last_price: 24_650,
    whatsapp_used: 0,
    whatsapp_limit: 20,
    levels: [],
    ...over
  };
}

describe('the blank form', () => {
  it('offers the six fixed slots, resistances above supports', () => {
    expect(emptyDraft().map((row) => row.label)).toEqual(['R3', 'R2', 'R1', 'S1', 'S2', 'S3']);
    expect(LEVEL_SLOTS.filter((slot) => slot.role === 'resistance')).toHaveLength(3);
    expect(LEVEL_SLOTS.filter((slot) => slot.role === 'support')).toHaveLength(3);
  });

  it('starts every price empty rather than at zero', () => {
    // A zero would be a *marked* level at an impossible price; blank is "not set".
    expect(emptyDraft().every((row) => row.price === '')).toBe(true);
  });
});

describe('seeding the form from the server', () => {
  it('fills slots by label and leaves the rest blank', () => {
    const saved: LevelPayload[] = [
      { label: 'R1', price: 24_700, role: 'resistance' },
      { label: 'S2', price: 24_500, role: 'support' }
    ];

    const draft = draftFrom(saved);

    expect(draft.find((r) => r.label === 'R1')?.price).toBe('24700');
    expect(draft.find((r) => r.label === 'S2')?.price).toBe('24500');
    expect(draft.find((r) => r.label === 'R3')?.price).toBe('');
  });

  it('keeps the server role, so a flipped level is not silently reset', () => {
    const draft = draftFrom([{ label: 'R1', price: 24_700, role: 'support' }]);
    expect(draft.find((r) => r.label === 'R1')?.role).toBe('support');
  });

  it('matches labels case-insensitively', () => {
    const draft = draftFrom([{ label: 'r1', price: 24_700, role: 'resistance' }]);
    expect(draft.find((r) => r.label === 'R1')?.price).toBe('24700');
  });
});

describe('building the payload', () => {
  it('drops blank rows instead of rejecting them', () => {
    // Marking four levels and leaving S3 empty is a normal morning.
    const draft = emptyDraft();
    draft[2]!.price = '24700';
    draft[3]!.price = '24600';

    expect(toPayload(draft).map((row) => row.label)).toEqual(['R1', 'S1']);
  });

  it('drops a row whose price is not a usable number', () => {
    const draft = emptyDraft();
    draft[2]!.price = 'abc';
    draft[3]!.price = '0';
    draft[4]!.price = '-5';

    expect(toPayload(draft)).toEqual([]);
  });
});

describe('validating the draft', () => {
  function draftOf(prices: Partial<Record<string, string>>) {
    return emptyDraft().map((row) => ({ ...row, price: prices[row.label] ?? '' }));
  }

  it('refuses an entirely empty form', () => {
    expect(validateDraft(emptyDraft())).toMatch(/at least one/i);
  });

  it('accepts a correctly ordered set', () => {
    expect(
      validateDraft(draftOf({ R1: '24700', S1: '24600', R2: '24800', S2: '24500' }))
    ).toBeNull();
  });

  it('accepts a partial set', () => {
    expect(validateDraft(draftOf({ R1: '24700' }))).toBeNull();
  });

  it('rejects a non-numeric price', () => {
    expect(validateDraft(draftOf({ R1: 'twenty' }))).toMatch(/R1 needs a positive price/);
  });

  it('rejects a support at or above a resistance', () => {
    // The rule worth enforcing: this would invert the ladder and make every
    // alert read backwards.
    expect(validateDraft(draftOf({ R1: '24600', S1: '24700' }))).toMatch(/above a resistance/);
    expect(validateDraft(draftOf({ R1: '24600', S1: '24600' }))).toMatch(/above a resistance/);
  });

  it('rejects two levels at the same price', () => {
    expect(validateDraft(draftOf({ R1: '24700', R2: '24700' }))).toMatch(/same price/);
  });

  it('does not complain about ordering when only one side is marked', () => {
    expect(validateDraft(draftOf({ R1: '24700', R2: '24800' }))).toBeNull();
    expect(validateDraft(draftOf({ S1: '24600', S2: '24500' }))).toBeNull();
  });
});

describe('the feed verdict', () => {
  it('says closed outside market hours, whatever the last tick was', () => {
    expect(feedVerdict(engine({ market_open: false }), NOW)).toBe('closed');
  });

  it('says live when a tick arrived recently', () => {
    expect(feedVerdict(engine(), NOW + 10_000)).toBe('live');
  });

  it('says stale when the market is open but the feed has gone quiet', () => {
    // The case that matters: this is a dead watcher, not a dull market, and the
    // page has to be the thing that tells them apart.
    expect(feedVerdict(engine(), NOW + 120_000)).toBe('stale');
  });

  it('holds the boundary at the staleness threshold', () => {
    expect(feedVerdict(engine(), NOW + 90_000)).toBe('live');
    expect(feedVerdict(engine(), NOW + 91_000)).toBe('stale');
  });

  it('says waiting before the first tick of the session', () => {
    expect(feedVerdict(engine({ last_tick_at: null }), NOW)).toBe('waiting');
  });

  it('says waiting when the state has not loaded yet', () => {
    expect(feedVerdict(undefined, NOW)).toBe('waiting');
  });

  it('treats an unparseable timestamp as no tick rather than as fresh', () => {
    expect(feedVerdict(engine({ last_tick_at: 'not a date' }), NOW)).toBe('waiting');
  });
});

describe('seconds since', () => {
  it('counts forward from the tick', () => {
    expect(secondsSince(TICK, NOW + 45_000)).toBe(45);
  });

  it('never returns a negative age', () => {
    // A clock skew between browser and server must not render as "-3s ago".
    expect(secondsSince(TICK, NOW - 5_000)).toBe(0);
  });

  it('returns null for a missing or invalid stamp', () => {
    expect(secondsSince(null, NOW)).toBeNull();
    expect(secondsSince('nope', NOW)).toBeNull();
  });
});

describe('role flips', () => {
  it('spots a broken resistance now acting as support', () => {
    expect(hasFlipped(level({ label: 'R1', role: 'support' }))).toBe(true);
  });

  it('spots a broken support now acting as resistance', () => {
    expect(hasFlipped(level({ label: 'S2', role: 'resistance' }))).toBe(true);
  });

  it('reports no flip while a level still does what its label says', () => {
    expect(hasFlipped(level({ label: 'R1', role: 'resistance' }))).toBe(false);
    expect(hasFlipped(level({ label: 'S1', role: 'support' }))).toBe(false);
  });
});

describe('state presentation', () => {
  it('gives every state a word and a glyph, not just a colour', () => {
    // The accessibility contract: state has to survive greyscale, colour-vision
    // deficiency and forced-colours mode.
    for (const state of ['idle', 'approaching', 'touched', 'break_pending', 'broken'] as const) {
      const look = stateLook(state);
      expect(look.label.length).toBeGreaterThan(0);
      expect(look.glyph.length).toBeGreaterThan(0);
    }
  });

  it('weights a confirmed break above an observation', () => {
    expect(stateLook('broken').tone).toBe('alert');
    expect(stateLook('idle').tone).toBe('neutral');
  });
});

describe('the ladder scale', () => {
  it('puts the highest value at the top and the lowest at the bottom', () => {
    const scale = ladderScale([{ level_price: 24_800 }, { level_price: 24_600 }], null);
    expect(scale).not.toBeNull();
    expect(scale!(24_800)).toBeLessThan(scale!(24_600));
  });

  it('keeps every position inside the frame', () => {
    const scale = ladderScale([{ level_price: 24_800 }, { level_price: 24_600 }], 24_700);
    for (const value of [24_800, 24_700, 24_600]) {
      expect(scale!(value)).toBeGreaterThanOrEqual(0);
      expect(scale!(value)).toBeLessThanOrEqual(1);
    }
  });

  it('includes the price in the extent, so a price beyond every level still fits', () => {
    const scale = ladderScale([{ level_price: 24_700 }, { level_price: 24_600 }], 25_000);
    expect(scale!(25_000)).toBeGreaterThanOrEqual(0);
    expect(scale!(25_000)).toBeLessThan(scale!(24_700));
  });

  it('returns null when there is nothing to scale against', () => {
    // One level and no price is a line with nothing to be relative to; the
    // caller omits the picture rather than drawing a degenerate one.
    expect(ladderScale([{ level_price: 24_700 }], null)).toBeNull();
    expect(ladderScale([], null)).toBeNull();
  });

  it('returns null when every value is identical', () => {
    expect(ladderScale([{ level_price: 24_700 }, { level_price: 24_700 }], 24_700)).toBeNull();
  });
});

describe('the watchable instruments', () => {
  it('offers exactly the three indices', () => {
    expect([...WATCHABLE]).toEqual(['NIFTY', 'BANKNIFTY', 'SENSEX']);
  });

  it('keeps a watchable selection', () => {
    expect(watchableOr('BANKNIFTY', 'NIFTY')).toBe('BANKNIFTY');
    expect(watchableOr('sensex', 'NIFTY')).toBe('SENSEX');
  });

  it('falls back when the terminal-wide picker is on a stock', () => {
    // `useSelectedInstrument` is shared with nineteen other pages and may well
    // be on RELIANCE. Showing an instrument this page cannot watch, and then
    // reporting it as having no levels, would read as a bug.
    expect(watchableOr('RELIANCE', 'NIFTY')).toBe('NIFTY');
    expect(watchableOr(undefined, 'NIFTY')).toBe('NIFTY');
    expect(watchableOr('', 'SENSEX')).toBe('SENSEX');
  });
});

describe('describing a band', () => {
  it('shows the multiple and the resolved points together', () => {
    // A multiple alone is abstract; points alone cannot be compared across
    // instruments. The setting is only legible as both.
    expect(describeBand(42, 700, 12)).toBe('0.060 x ATR = 42.0 pts');
  });

  it('names the default when there is no ATR to derive a multiple from', () => {
    // Not a repeat of the warning the panel header already carries, and not
    // an echo of the input's own value — the default is the one thing the
    // row can usefully add.
    expect(describeBand(12, null, 12)).toBe('Default 12 pts');
    expect(describeBand(30, 0, 12)).toBe('Default 12 pts');
  });

  it('names the default rather than the override currently typed in', () => {
    expect(describeBand(45, null, 12)).toBe('Default 12 pts');
  });
});

describe('the band warning', () => {
  it('is silent when bands are scaled', () => {
    expect(bandWarning(BANDS)).toBeNull();
  });

  it('explains that unscaled bands are NIFTY-sized', () => {
    // The whole bug, in one sentence the reader can act on.
    const warning = bandWarning({ ...BANDS, source: 'points', atr: null });
    expect(warning).toMatch(/ATR unavailable/i);
    expect(warning).toMatch(/NIFTY/);
  });

  it('surfaces an ignored override ahead of the generic message', () => {
    const warning = bandWarning({ ...BANDS, note: 'Override ignored: touch band too wide' });
    expect(warning).toMatch(/Override ignored/);
  });

  it('is silent when there is no state yet', () => {
    expect(bandWarning(undefined)).toBeNull();
  });
});

describe('override parsing', () => {
  it('reads a blank field as "use the default", not as zero', () => {
    // Load-bearing: a zero touch band would mean a level can never be touched.
    expect(parseOverride('')).toBeNull();
    expect(parseOverride('   ')).toBeNull();
  });

  it('reads zero as zero where zero is a real setting', () => {
    expect(parseOverride('0')).toBe(0);
  });

  it('reads a number', () => {
    expect(parseOverride('42.5')).toBe(42.5);
  });

  it('treats unparseable text as unset rather than as NaN', () => {
    expect(parseOverride('abc')).toBeNull();
  });

  it('round-trips through the input text', () => {
    expect(overrideText(null)).toBe('');
    expect(overrideText(0)).toBe('0');
    expect(overrideText(42.5)).toBe('42.5');
  });
});

describe('validating overrides', () => {
  const none = { ...EMPTY_OVERRIDES };

  it('accepts an all-default set', () => {
    expect(validateOverrides(none)).toBeNull();
  });

  it('rejects a non-positive distance', () => {
    expect(validateOverrides({ ...none, touch: 0 })).toMatch(/above zero/);
    expect(validateOverrides({ ...none, break_buffer: -1 })).toMatch(/above zero/);
  });

  it('allows a zero cooldown but not a negative one', () => {
    expect(validateOverrides({ ...none, cooldown_minutes: 0 })).toBeNull();
    expect(validateOverrides({ ...none, cooldown_minutes: -1 })).toMatch(/Cooldown/);
  });

  it('requires a cap of at least one', () => {
    expect(validateOverrides({ ...none, daily_alert_cap: 0 })).toMatch(/at least one/);
    expect(validateOverrides({ ...none, daily_alert_cap: 1 })).toBeNull();
  });

  it('rejects a touch band wider than the approach band', () => {
    expect(validateOverrides({ ...none, touch: 50, approach: 25 })).toMatch(/TOUCHED/);
  });

  it('does not compare a lone override against a value it cannot see', () => {
    // The other half is ATR-scaled and the browser has no ATR; the API
    // reports that case instead of guessing here.
    expect(validateOverrides({ ...none, touch: 500 })).toBeNull();
  });
});

describe('the alert channel step', () => {
  const base = {
    channel: 'telegram' as const,
    configured: true,
    ready: true,
    verified: true,
    enabled: true,
    label: '@my_alerts_bot',
    target: '12345',
    masked_secret: '8123******AAH1'
  };

  it('is disconnected before a token is saved', () => {
    expect(channelStep(undefined)).toBe('disconnected');
    expect(channelStep({ ...base, configured: false })).toBe('disconnected');
  });

  it('needs a chat once the token is in but nothing is linked', () => {
    // The normal first run: a bot cannot open a conversation, so the user has
    // to message it before there is a chat to find.
    expect(channelStep({ ...base, target: null, ready: false })).toBe('needs-chat');
    expect(channelStep({ ...base, verified: false, ready: false })).toBe('needs-chat');
  });

  it('is paused when connected but switched off', () => {
    expect(channelStep({ ...base, enabled: false, ready: false })).toBe('paused');
  });

  it('is ready only when every part is in place', () => {
    expect(channelStep(base)).toBe('ready');
  });

  it('gives every step a label and a detail, so none renders blank', () => {
    for (const step of ['disconnected', 'needs-chat', 'paused', 'ready'] as const) {
      expect(CHANNEL_STEP_COPY[step].label.length).toBeGreaterThan(0);
      expect(CHANNEL_STEP_COPY[step].detail.length).toBeGreaterThan(0);
    }
  });
});

describe('the stale-levels warning', () => {
  it('is silent when the levels are current', () => {
    expect(staleWarning(engine())).toBeNull();
    expect(staleWarning(engine({ levels_stale: false }))).toBeNull();
  });

  it('says when they were marked and that nothing will fire', () => {
    // The one state where a quiet phone is correct, so the page has to be
    // explicit rather than leaving silence to be interpreted.
    const warning = staleWarning(engine({ levels_stale: true, marked_on: '2026-10-30' }));
    expect(warning).toMatch(/2026-10-30/);
    expect(warning).toMatch(/No alerts will be sent/);
    expect(warning).toMatch(/re-mark/);
  });

  it('copes with levels that were never stamped', () => {
    const warning = staleWarning(engine({ levels_stale: true, marked_on: null }));
    expect(warning).toMatch(/an earlier session/);
  });

  it('is silent before the state has loaded', () => {
    expect(staleWarning(undefined)).toBeNull();
  });
});

describe('the marked-for note', () => {
  it('states the session the levels are for', () => {
    // The positive half of the staleness fact. Answering "are today's levels
    // loaded?" with an absent warning asks the reader to trust that the
    // warning would have shown — the trust a missed alert destroys.
    expect(markedNote(engine({ marked_on: '2026-11-02' }))).toBe('Marked for 2026-11-02');
  });

  it('says nothing when the levels are stale', () => {
    // The banner is already saying it, louder.
    expect(markedNote(engine({ marked_on: '2026-10-30', levels_stale: true }))).toBeNull();
  });

  it('says nothing when no levels are marked at all', () => {
    expect(markedNote(engine({ marked_on: null }))).toBeNull();
    expect(markedNote(undefined)).toBeNull();
  });
});
