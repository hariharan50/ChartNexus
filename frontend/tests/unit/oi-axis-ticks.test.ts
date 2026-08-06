import { describe, expect, it } from 'vitest';
import {
  axisTicks,
  type OiSeriesFrame
} from '../../app/routes/terminal/options/open-interest/oi-data';

/**
 * The hour marks under the OI time slider.
 *
 * The load-bearing property is that ticks are positioned by *frame index*, not
 * by clock time. They coincide only while the ingest cadence is even; after a
 * gap they diverge, and index-positioning is the one that keeps a label under
 * the frame it names — because that is also how the handle moves.
 */

/** IST instant as a UTC ISO string. 09:15 IST is 03:45 UTC. */
function ist(hour: number, minute: number): string {
  const utcMinutes = hour * 60 + minute - (5 * 60 + 30);
  return new Date(Date.UTC(2026, 7, 5, 0, utcMinutes)).toISOString();
}

function frame(hour: number, minute: number): OiSeriesFrame {
  return { t: ist(hour, minute), strikes: [], call: [], put: [] };
}

/** A full 09:15→15:30 session at the 180-second ingest cadence. */
function session(): OiSeriesFrame[] {
  const frames: OiSeriesFrame[] = [];
  for (let minutes = 9 * 60 + 15; minutes <= 15 * 60 + 30; minutes += 3) {
    frames.push(frame(Math.floor(minutes / 60), minutes % 60));
  }
  return frames;
}

describe('axisTicks', () => {
  it('labels every hour of a full session', () => {
    const labels = axisTicks(session())
      .map((t) => t.label)
      .filter((label): label is string => label !== null);

    expect(labels).toEqual(['9 am', '10 am', '11 am', '12 pm', '1 pm', '2 pm', '3 pm']);
  });

  it('marks the half hours without labelling them', () => {
    const ticks = axisTicks(session());

    // 09:15 opens the 9:00 bucket, then 09:30, 10:00 … 15:30 — 14 in all.
    expect(ticks).toHaveLength(14);
    expect(ticks.filter((t) => t.label === null)).toHaveLength(7);
  });

  it('positions ticks by frame index, not by clock time', () => {
    // A deliberately uneven series: a two-hour ingest gap between the second and
    // third frames. By the clock the 11 am tick would sit near the middle; by
    // index it belongs two thirds along, under the frame that carries it.
    const gappy = [frame(9, 15), frame(9, 18), frame(11, 0), frame(11, 3)];

    const eleven = axisTicks(gappy).find((t) => t.label === '11 am');

    expect(eleven?.index).toBe(2);
    expect(eleven?.pct).toBeCloseTo((2 / 3) * 100);
  });

  it('starts at the left edge and ends at the right', () => {
    const ticks = axisTicks(session());

    expect(ticks[0]!.pct).toBe(0);
    expect(ticks.at(-1)!.pct).toBe(100);
  });

  it('gives every tick a distinct frame', () => {
    const indices = axisTicks(session()).map((t) => t.index);

    expect(new Set(indices).size).toBe(indices.length);
    expect([...indices]).toEqual([...indices].sort((a, b) => a - b));
  });

  it('handles the two-point live tier without throwing', () => {
    // The `live_proxy` fallback: session open and now, nothing between.
    const ticks = axisTicks([frame(9, 15), frame(12, 0)]);

    expect(ticks.length).toBeLessThanOrEqual(2);
    expect(ticks.map((t) => t.label)).toEqual(['9 am', '12 pm']);
  });

  it('returns nothing when there is nothing to scrub', () => {
    expect(axisTicks([])).toEqual([]);
    expect(axisTicks([frame(9, 15)])).toEqual([]);
  });
});
