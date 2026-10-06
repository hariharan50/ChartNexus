import { describe, expect, it } from 'vitest';
import {
  coverageNote,
  exchangeOf,
  formatMoney,
  sessionsOf,
  signOf,
  strikeLabel,
  tradeTime,
  type PnlTrade,
  type StraddlePnlView
} from '../../app/routes/terminal/tools/straddle-pnl/pnl-data';

function trade(over: Partial<PnlTrade> = {}): PnlTrade {
  return {
    type: 'ENTRY',
    t: '2026-10-05T03:45:00+00:00',
    strike: 22550,
    old_strike: null,
    ce_price: 110.75,
    pe_price: 82.95,
    straddle: 193.7,
    exit_ce: null,
    exit_pe: null,
    exit_straddle: null,
    spot: 22544.5,
    leg_pnl: null,
    cumulative_pnl: 0,
    ...over
  };
}

function view(over: Partial<StraddlePnlView> = {}): StraddlePnlView {
  return {
    instrument_id: 'NIFTY',
    symbol: 'NIFTY',
    expiry_date: '2026-10-06',
    lot_size: 65,
    lots: 1,
    quantity: 65,
    adjustment_points: 50,
    strike_step: 50,
    requested_sessions: 1,
    covered_sessions: 1,
    open_ts: '2026-10-05T03:45:00+00:00',
    now_ts: '2026-10-05T10:00:00+00:00',
    spot: 22555.75,
    entry_strike: 22550,
    data_quality: 'intraday',
    summary: { total_pnl: -988, max_pnl: 152.75, min_pnl: -2548, total_adjustments: 42 },
    series: [],
    trades: [],
    ...over
  };
}

describe('money formatting', () => {
  it('separates thousands and always shows two places', () => {
    expect(formatMoney(-2548)).toBe('-2,548.00');
    expect(formatMoney(152.75)).toBe('152.75');
    expect(formatMoney(0)).toBe('0.00');
  });
});

describe('trade times', () => {
  it('reads in IST, 24-hour, with no meridiem', () => {
    // 03:45 UTC is 09:15 IST — the bell.
    expect(tradeTime('2026-10-05T03:45:00+00:00')).toBe('05 Oct 09:15');
  });

  it('never prints a PM suffix on an afternoon capture', () => {
    // The tool this clones renders "13:18 PM", which is the bug being fixed.
    const label = tradeTime('2026-10-05T07:48:00+00:00');
    expect(label).toBe('05 Oct 13:18');
    expect(label).not.toMatch(/[AP]M/);
  });
});

describe('the strike column', () => {
  it('names one strike when the position just holds it', () => {
    expect(strikeLabel(trade())).toBe('22550');
  });

  it('shows the move when a trade re-struck', () => {
    expect(strikeLabel(trade({ type: 'ADJUSTMENT', old_strike: 22550, strike: 22500 }))).toBe(
      '22550 → 22500'
    );
  });
});

describe('sign of a money cell', () => {
  it('paints gains and losses, and leaves an exact zero neutral', () => {
    expect(signOf(152.75)).toBe('pos');
    expect(signOf(-308.75)).toBe('neg');
    expect(signOf(0)).toBe('flat');
  });

  it('leaves an entry’s absent leg P&L neutral rather than green', () => {
    expect(signOf(null)).toBe('flat');
  });
});

describe('ranges', () => {
  it('maps every label to its session count', () => {
    expect(sessionsOf('1')).toBe(1);
    expect(sessionsOf('7')).toBe(7);
    expect(sessionsOf('10')).toBe(10);
  });

  it('falls back to one session for an unknown range', () => {
    expect(sessionsOf('99')).toBe(1);
  });
});

describe('exchanges', () => {
  it('knows where each index’s options list', () => {
    expect(exchangeOf('NIFTY')).toBe('NFO');
    expect(exchangeOf('BANKNIFTY')).toBe('NFO');
    expect(exchangeOf('SENSEX')).toBe('BFO');
  });
});

describe('coverage note', () => {
  it('says nothing when the archive covered what was asked', () => {
    expect(coverageNote(view())).toBeNull();
  });

  it('says so when the archive is short of the window', () => {
    const note = coverageNote(view({ requested_sessions: 5, covered_sessions: 2 }));
    expect(note).toContain('2 of 5');
  });

  it('explains an empty archive rather than showing a flat zero line', () => {
    const note = coverageNote(view({ data_quality: 'empty', covered_sessions: 0 }));
    expect(note).toContain('ingest worker');
  });

  it('has nothing to say before the first run', () => {
    expect(coverageNote(undefined)).toBeNull();
  });
});
