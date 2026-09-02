import { describe, expect, it } from 'vitest';
import {
  fmtPcr,
  fmtPct,
  normalizeFromOpen
} from '../../app/routes/terminal/options/price-vs-oi/price-vs-oi-data';

/**
 * The Price vs OI charts normalise each leg to its own open so a call and a put
 * at different price levels compare on one axis. That arithmetic — and the labels
 * either side of it — is what these pin.
 */

describe('normalizeFromOpen', () => {
  it('reads each point as a fraction of the session open', () => {
    // Open 100: 120 → +0.2, 80 → -0.2.
    expect(normalizeFromOpen([100, 120, 80])).toEqual([0, 0.2, -0.2]);
  });

  it('anchors on the first real point when the open is missing', () => {
    expect(normalizeFromOpen([null, 200, 300])).toEqual([null, 0, 0.5]);
  });

  it('keeps a null point null rather than bridging it', () => {
    expect(normalizeFromOpen([100, null, 150])).toEqual([0, null, 0.5]);
  });

  it('voids the whole series when the open is zero (nothing to divide by)', () => {
    expect(normalizeFromOpen([0, 10, 20])).toEqual([null, null, null]);
  });

  it('is all-null for an empty or all-null series', () => {
    expect(normalizeFromOpen([])).toEqual([]);
    expect(normalizeFromOpen([null, null])).toEqual([null, null]);
  });
});

describe('formatting', () => {
  it('formats the normalised axis as a signed percentage', () => {
    expect(fmtPct(0.124)).toBe('+12.4%');
    expect(fmtPct(-0.05)).toBe('-5.0%');
    expect(fmtPct(0)).toBe('+0.0%');
  });

  it('formats the PCR to two decimals', () => {
    expect(fmtPcr(1.489)).toBe('1.49');
  });
});
