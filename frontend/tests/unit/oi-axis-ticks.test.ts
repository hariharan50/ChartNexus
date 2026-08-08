import { describe, expect, it } from 'vitest';
import {
  axisTicks,
  sessionPositions,
  sessionTicks,
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

describe('label crowding', () => {
  it('drops a label that would overprint its neighbour, keeping the tick', () => {
    // The shape of a day the worker joined late: a derived 9:15 baseline, then
    // real captures from 1 pm. "9 am" and "1 pm" land ~2% apart and used to
    // render as the unreadable "9 am1 pm".
    const lateStart = [frame(9, 15), ...Array.from({ length: 56 }, (_, i) => frame(13, 1 + i))];

    const ticks = axisTicks(lateStart);
    const onePm = ticks.find((t) => t.index === 1);

    expect(ticks[0]!.label).toBe('9 am');
    expect(onePm).toBeDefined();
    expect(onePm!.label).toBeNull(); // the mark stays, the text goes
    expect(ticks.filter((t) => t.label === '9 am1 pm')).toHaveLength(0);
  });

  it('still labels hours once they are far enough apart', () => {
    // Same late start, but now well into the afternoon: 2 pm and 3 pm have room.
    const lateStart = [frame(9, 15), ...Array.from({ length: 130 }, (_, i) => frame(13, 1 + i))];

    const labels = axisTicks(lateStart)
      .map((t) => t.label)
      .filter((l): l is string => l !== null);

    expect(labels).toContain('9 am');
    expect(labels).toContain('2 pm');
    expect(labels).toContain('3 pm');
  });

  it('leaves an evenly-recorded session fully labelled', () => {
    // The regression guard: crowding logic must not eat labels on a normal day.
    const labels = axisTicks(session())
      .map((t) => t.label)
      .filter((l): l is string => l !== null);

    expect(labels).toEqual(['9 am', '10 am', '11 am', '12 pm', '1 pm', '2 pm', '3 pm']);
  });
});

/**
 * The session-length track, used where the question is "what did the book look
 * like at this time" rather than "what changed between these two snapshots".
 *
 * Its whole reason to exist is the case `axisTicks` cannot express: a day whose
 * ingest started late. Index positioning stretches those frames across the full
 * width and draws a two-hour afternoon as a complete trading day.
 */
describe('sessionPositions', () => {
  it('places the bell at the left edge and the F&O close at the right', () => {
    // 15:40, not 15:30: derivatives run ten minutes past the cash close, and a
    // track that ended at 15:30 stacked every later capture on the right edge.
    expect(sessionPositions([ist(9, 15), ist(15, 40)])).toEqual([0, 100]);
  });

  it('places a frame by the clock, not by how many frames precede it', () => {
    // 11:45 is 150 minutes into a 385-minute session — 38.96% along, whatever
    // the ingest cadence was, and whether or not it was the second frame.
    const [, mid] = sessionPositions([ist(9, 15), ist(11, 45), ist(15, 40)]);
    const [, denser] = sessionPositions([ist(9, 15), ist(11, 45), ist(12, 0), ist(15, 40)]);

    expect(mid).toBeCloseTo((150 / 385) * 100, 6);
    expect(denser).toBe(mid);
  });

  it('keeps the cash close and the F&O close at different positions', () => {
    // Both used to land on 100. The ten minutes between them are a real part of
    // the derivatives session and have to be scrubbable.
    const [cash, fno] = sessionPositions([ist(15, 30), ist(15, 40)]);

    expect(cash).toBeLessThan(100);
    expect(fno).toBe(100);
  });

  it('leaves the morning empty when recording started at lunchtime', () => {
    // The case the user hit: ingest began at 1:01 pm. On an index track this
    // frame would sit at 0 and the timeline would claim to start there.
    const [first] = sessionPositions([ist(13, 1), ist(15, 28)]);

    expect(first).toBeGreaterThan(55);
  });

  it('clamps a capture either side of the bell rather than dropping it', () => {
    // A pre-open or post-close capture is a real observation; it belongs at the
    // end of the track, not off it.
    expect(sessionPositions([ist(9, 0), ist(15, 50)])).toEqual([0, 100]);
  });
});

describe('sessionTicks', () => {
  it('names every hour inside the session', () => {
    const labels = sessionTicks()
      .map((tick) => tick.label)
      .filter((label): label is string => label !== null);

    expect(labels).toEqual(['10 am', '11 am', '12 pm', '1 pm', '2 pm', '3 pm']);
  });

  it('marks the bell and the close without labelling them', () => {
    // The caller prints both times either side of the track; at 375px
    // "9:15 am" and "10 am" would overprint.
    const ticks = sessionTicks();

    expect(ticks[0]).toMatchObject({ pct: 0, label: null });
    expect(ticks[ticks.length - 1]).toMatchObject({ pct: 100, label: null });
  });

  it('is fixed geometry, so the track means the same on every day', () => {
    expect(sessionTicks()).toEqual(sessionTicks());
  });
});
