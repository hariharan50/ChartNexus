import { describe, expect, it } from 'vitest';
import {
  frameHeadFor,
  smartOiCsv,
  toCandles,
  toFlowBars,
  toVolumeBars,
  windowLabel,
  type SmartOiBar,
  type SmartOiView
} from '../../app/routes/terminal/options/smart-oi/smart-oi-data';

/**
 * Smart OI does its windowing and bucketing on the server, so what is left here
 * is the join between the payload and the two chart libraries — which is
 * exactly where the page's two axes can quietly be crossed.
 */

const BARS: SmartOiBar[] = [
  { t: '2026-08-20T03:45:00+00:00', o: 100, h: 110, l: 95, c: 105 },
  { t: '2026-08-20T03:50:00+00:00', o: 105, h: 115, l: 104, c: 112 },
  { t: '2026-08-20T03:55:00+00:00', o: 112, h: 113, l: 100, c: 101 }
];

describe('toCandles', () => {
  it('converts to epoch seconds, not milliseconds', () => {
    // The chart library silently mis-scales a millisecond value into the year
    // 56,000 rather than rejecting it, so the bug presents as an empty chart.
    const candles = toCandles(BARS);

    expect(candles[0]!.time).toBe(Date.parse(BARS[0]!.t) / 1000);
    expect(candles[0]!.time).toBeLessThan(4_000_000_000);
  });

  it('carries every OHLC leg through', () => {
    const [first] = toCandles(BARS);

    expect(first).toMatchObject({ open: 100, high: 110, low: 95, close: 105 });
  });
});

describe('toFlowBars', () => {
  const COLORS = { up: 'green', down: 'red' };

  it('colours by the sign of each bar, not by one series colour', () => {
    const flow = toFlowBars(BARS, [500, -200, 0], COLORS);

    expect(flow.map((bar) => bar.color)).toEqual(['green', 'red', 'green']);
  });

  it('keeps a null as a null rather than folding it to zero', () => {
    // The chart drops nulls to leave a real gap. Folding to 0 would draw a
    // zero-height bar, which claims nothing was written in that bar — a
    // different statement from "nothing was observed".
    const flow = toFlowBars(BARS, [500, null, 300], COLORS);

    expect(flow[1]!.value).toBeNull();
    expect(flow).toHaveLength(BARS.length);
  });

  it('pads a short values array rather than dropping bars', () => {
    const flow = toFlowBars(BARS, [500], COLORS);

    expect(flow).toHaveLength(3);
    expect(flow[2]!.value).toBeNull();
  });
});

describe('toVolumeBars', () => {
  it('uses one colour for the whole series', () => {
    const bars = toVolumeBars(BARS, [10, 20, 30], 'blue');

    expect(bars.every((bar) => bar.color === 'blue')).toBe(true);
  });
});

describe('frameHeadFor', () => {
  // The frame axis runs at the archive's cadence, the bar axis at the chart's.
  // They have different lengths, so a replay head crosses between them by
  // timestamp — sharing an index would sweep the two panels apart.
  const TIMES = [
    '2026-08-20T03:45:00+00:00',
    '2026-08-20T03:46:00+00:00',
    '2026-08-20T03:52:00+00:00',
    '2026-08-20T03:58:00+00:00'
  ];

  it('resolves to the last capture at or before the bar', () => {
    expect(frameHeadFor(TIMES, BARS, 1)).toBe(1);
  });

  it('advances as the head moves', () => {
    expect(frameHeadFor(TIMES, BARS, 2)).toBe(2);
  });

  it('is -1 before the first capture', () => {
    const late = ['2026-08-20T04:00:00+00:00'];

    expect(frameHeadFor(late, BARS, 0)).toBe(-1);
  });

  it('falls back to the newest frame when the head is off the bar axis', () => {
    expect(frameHeadFor(TIMES, BARS, 99)).toBe(TIMES.length - 1);
  });
});

describe('windowLabel', () => {
  it('reads as the strike range the toolbar shows', () => {
    expect(windowLabel(21200, 27200)).toBe('(21,200 - 27,200)');
  });

  it('is empty when there is no chain to window', () => {
    expect(windowLabel(null, null)).toBe('');
  });
});

describe('smartOiCsv', () => {
  it('exports the bar axis with a blank where a bar had no capture', () => {
    const view = {
      bars: BARS,
      smart_oi: [500, null, -200],
      call_vol: [10, null, 30],
      put_vol: [20, null, 40]
    } as SmartOiView;

    const lines = smartOiCsv(view).split('\n');

    expect(lines[0]).toBe('time,open,high,low,close,smart_oi,call_volume,put_volume');
    expect(lines).toHaveLength(4);
    expect(lines[2]).toBe('2026-08-20T03:50:00+00:00,105,115,104,112,,,');
    expect(lines[3]).toBe('2026-08-20T03:55:00+00:00,112,113,100,101,-200,30,40');
  });
});
