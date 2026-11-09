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
  alertLook,
  describeAlert,
  describeChannels,
  detectPreset,
  formatSessionDate,
  gapToNextBelow,
  ladderScaleX,
  nearestLevel,
  presetOverrides,
  PRESET_COPY,
  resolvedDefaults,
  signedPoints,
  type AlertItem,
  type EngineState,
  type ResolvedBands,
  type LevelPayload,
  type Settings,
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

function logged(over: Partial<AlertItem> = {}): AlertItem {
  return {
    kind: 'touched',
    label: 'R1',
    level_price: 24_700,
    price: 24_703,
    role_before: 'resistance',
    role_after: 'resistance',
    at: TICK,
    channels: ['telegram'],
    ...over
  };
}

function sensitivity(over: Partial<Settings> = {}): Settings {
  return {
    symbol: 'NIFTY',
    bands: BANDS,
    cooldown_minutes: 20,
    daily_alert_cap: 3,
    defaults: {
      touch_multiple: 0.03,
      approach_multiple: 0.125,
      break_multiple: 0.06,
      atr_period: 14,
      confirm_hold_seconds: 20,
      cooldown_minutes: 20,
      daily_alert_cap: 3,
      fallback_touch: 6,
      fallback_approach: 25,
      fallback_break_buffer: 12
    },
    overrides: EMPTY_OVERRIDES,
    ...over
  };
}

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

describe('the horizontal price map scale', () => {
  const levels = [{ level_price: 24_900 }, { level_price: 24_400 }];

  it('puts the lowest price on the left and the highest on the right', () => {
    const scale = ladderScaleX(levels, null);
    expect(scale).not.toBeNull();
    expect(scale!(24_400)).toBeLessThan(scale!(24_900));
  });

  it('keeps every position inside the frame', () => {
    const scale = ladderScaleX(levels, 24_650)!;
    for (const value of [24_400, 24_650, 24_900]) {
      expect(scale(value)).toBeGreaterThanOrEqual(0);
      expect(scale(value)).toBeLessThanOrEqual(1);
    }
  });

  it('mirrors the vertical scale exactly, so the two cannot disagree', () => {
    // Both pictures place the same cursor against the same ticks; a second
    // padding constant is the bug this pins shut.
    const vertical = ladderScale(levels, 24_650)!;
    const horizontal = ladderScaleX(levels, 24_650)!;
    expect(horizontal(24_650)).toBeCloseTo(1 - vertical(24_650), 10);
  });

  it('returns null when there is nothing to scale against', () => {
    expect(ladderScaleX([{ level_price: 24_700 }], null)).toBeNull();
  });
});

describe('naming a session', () => {
  it('reads as a weekday and a date, which is what makes a stale set obvious', () => {
    expect(formatSessionDate('2026-11-02')).toBe('Mon 2 Nov');
  });

  it('reads a full timestamp in IST, not UTC', () => {
    // 23:00 UTC is already the next day in Kolkata, and the session stamp has
    // to agree with the market the trader is in.
    expect(formatSessionDate('2026-11-02T23:00:00Z')).toBe('Tue 3 Nov');
  });

  it('degrades to a dash rather than "Invalid Date"', () => {
    expect(formatSessionDate(null)).toBe('—');
    expect(formatSessionDate(undefined)).toBe('—');
    expect(formatSessionDate('not a date')).toBe('—');
  });
});

describe('the nearest level', () => {
  const levels: WatcherState[] = [
    level({ label: 'R2', level_price: 24_800 }),
    level({ label: 'R1', level_price: 24_700 }),
    level({ label: 'S1', level_price: 24_600 })
  ];

  it('picks the closest in either direction', () => {
    expect(nearestLevel(levels, 24_690)?.level.label).toBe('R1');
    expect(nearestLevel(levels, 24_610)?.level.label).toBe('S1');
  });

  it('reports an unsigned distance', () => {
    // Unsigned on purpose: a signed number in this slot reads as a P&L.
    expect(nearestLevel(levels, 24_610)?.distance).toBeCloseTo(10);
    expect(nearestLevel(levels, 24_810)?.distance).toBeCloseTo(10);
  });

  it('keeps the first of two equally close levels rather than flickering', () => {
    // Price exactly between R1 and S1. A strict comparison means the earlier
    // one wins, so the callout does not alternate on every tick.
    expect(nearestLevel(levels, 24_650)?.level.label).toBe('R1');
  });

  it('is null before the first tick and when nothing is marked', () => {
    expect(nearestLevel(levels, null)).toBeNull();
    expect(nearestLevel([], 24_650)).toBeNull();
  });
});

describe('signed points', () => {
  it('uses a real minus sign so the column stays aligned', () => {
    expect(signedPoints(-152.4)).toBe('−152.40');
  });

  it('marks a positive gap explicitly', () => {
    expect(signedPoints(12.4)).toBe('+12.40');
  });

  it('treats zero as non-negative', () => {
    expect(signedPoints(0)).toBe('+0.00');
  });
});

describe('the gap to the next level below', () => {
  it('measures to the nearest lower mark, not the lowest', () => {
    expect(gapToNextBelow(24_700, [24_900, 24_700, 24_600, 24_400])).toBeCloseTo(100);
  });

  it('is null for the lowest mark, which has nothing below it', () => {
    expect(gapToNextBelow(24_400, [24_900, 24_700, 24_400])).toBeNull();
  });

  it('ignores a mark at the same price', () => {
    expect(gapToNextBelow(24_700, [24_700])).toBeNull();
  });
});

describe('presenting an alert', () => {
  it('gives every kind a word and a glyph, not just a colour', () => {
    for (const kind of [
      'approaching',
      'touched',
      'break_confirmed',
      'wick_rejected',
      'reclaimed',
      'gapped_through'
    ] as const) {
      const look = alertLook(kind);
      expect(look.label.length).toBeGreaterThan(0);
      expect(look.glyph.length).toBeGreaterThan(0);
    }
  });

  it('names a log entry in the past tense, so it does not read as a live state', () => {
    expect(alertLook('break_confirmed').label).toBe('Broke');
    expect(stateLook('broken').label).toBe('Broken');
  });

  it('marks a reclaim as a good outcome, which no level state can be', () => {
    expect(alertLook('reclaimed').tone).toBe('ok');
  });
});

describe('describing a logged alert', () => {
  it('says where price was relative to the level', () => {
    expect(describeAlert(logged({ price: 24_682.4, level_price: 24_700 }))).toBe(
      'Price 24,682.40, 17.6 pts below the level'
    );
  });

  it('says above when price was through it', () => {
    expect(describeAlert(logged({ price: 24_712, level_price: 24_700 }))).toContain(
      '12.0 pts above the level'
    );
  });

  it('states the role flip, which is the actionable half of a break', () => {
    expect(
      describeAlert(
        logged({
          kind: 'break_confirmed',
          role_before: 'resistance',
          role_after: 'support'
        })
      )
    ).toContain('now acting as support');
  });

  it('says nothing about roles when nothing flipped', () => {
    expect(describeAlert(logged())).not.toContain('acting as');
  });
});

describe('describing the channels an alert used', () => {
  it('names both when both took it', () => {
    expect(describeChannels(['telegram', 'whatsapp'])).toBe('Telegram · WhatsApp');
  });

  it('calls out a delivery that did not happen rather than showing a blank', () => {
    // The engine fired and nothing took it: a different fault from a quiet
    // morning, and invisible if this rendered as an empty string.
    expect(describeChannels([])).toBe('Not delivered');
  });
});

describe('sensitivity presets', () => {
  const scaled = sensitivity();
  const unscaled = sensitivity({
    bands: { ...sensitivity().bands, source: 'points', atr: null }
  });

  it('derives the defaults from the multiples and the live ATR', () => {
    // 0.03 x 200 = 6, 0.125 x 200 = 25, 0.06 x 200 = 12.
    expect(resolvedDefaults(scaled)).toEqual({ touch: 6, approach: 25, break_buffer: 12 });
  });

  it('falls back to the point defaults when there is no ATR', () => {
    expect(resolvedDefaults(unscaled)).toEqual({
      touch: 6,
      approach: 25,
      break_buffer: 12
    });
  });

  it('ignores an existing override when computing the defaults', () => {
    // `bands` has the override folded in already; scaling a preset from it
    // would compound on every click.
    const overridden = sensitivity({ bands: { ...sensitivity().bands, touch: 40 } });
    expect(resolvedDefaults(overridden).touch).toBe(6);
  });

  it('writes nulls for default, which is what "stop overriding" means', () => {
    expect(presetOverrides(scaled, 'default')).toEqual({
      touch: null,
      approach: null,
      break_buffer: null
    });
  });

  it('tightens all three bands together', () => {
    expect(presetOverrides(scaled, 'tight')).toEqual({
      touch: 4.2,
      approach: 17.5,
      break_buffer: 8.4
    });
  });

  it('widens all three bands together', () => {
    expect(presetOverrides(scaled, 'wide')).toEqual({
      touch: 9.6,
      approach: 40,
      break_buffer: 19.2
    });
  });

  it('keeps touch under approach at every preset, so the states stay ordered', () => {
    for (const preset of ['tight', 'wide'] as const) {
      const bands = presetOverrides(scaled, preset);
      expect(bands.touch!).toBeLessThan(bands.approach!);
    }
  });

  it('scales from points when ATR is unavailable, so the buttons still work', () => {
    expect(presetOverrides(unscaled, 'tight')).toEqual({
      touch: 4.2,
      approach: 17.5,
      break_buffer: 8.4
    });
  });

  it('reads an untouched set as default', () => {
    expect(detectPreset(scaled, EMPTY_OVERRIDES)).toBe('default');
  });

  it('recognises its own output', () => {
    for (const preset of ['tight', 'wide'] as const) {
      const draft = { ...EMPTY_OVERRIDES, ...presetOverrides(scaled, preset) };
      expect(detectPreset(scaled, draft)).toBe(preset);
    }
  });

  it('calls a hand-edited field custom rather than keeping the old label', () => {
    const draft = { ...EMPTY_OVERRIDES, ...presetOverrides(scaled, 'tight'), touch: 5 };
    expect(detectPreset(scaled, draft)).toBe('custom');
  });

  it('calls a partial override custom, not default', () => {
    expect(detectPreset(scaled, { ...EMPTY_OVERRIDES, approach: 30 })).toBe('custom');
  });

  it('ignores the throttles, which no preset touches', () => {
    const draft = { ...EMPTY_OVERRIDES, cooldown_minutes: 5, daily_alert_cap: 9 };
    expect(detectPreset(scaled, draft)).toBe('default');
  });

  it('gives every preset a name and a sentence saying what it does', () => {
    // Including `custom`, which is never clicked but is always displayable:
    // the control has to be able to show the state it detects.
    for (const preset of ['tight', 'default', 'wide', 'custom'] as const) {
      expect(PRESET_COPY[preset].label.length).toBeGreaterThan(0);
      expect(PRESET_COPY[preset].detail.length).toBeGreaterThan(0);
    }
  });
});
