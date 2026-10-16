import { describe, expect, it } from 'vitest';
import { emptyReason } from '../../app/lib/contexts/instrument-catalog/coverage';

/**
 * What an empty panel says.
 *
 * The distinction is not cosmetic. Options Lab gets per-strike OI live for any
 * contract, but the *intraday* shape of it comes from an archive that captures
 * indices only. So an empty gamma panel on NIFTY means "not yet today" and the
 * same panel on ITC means "not ever, under the current settings" — telling a
 * stock reader to wait is simply false.
 */

describe('emptyReason', () => {
  it('tells an index that today has not filled in yet', () => {
    const text = emptyReason({
      symbol: 'NIFTY',
      kind: 'index',
      feature: 'gamma profile',
      historical: false
    });

    expect(text).toContain('today');
    expect(text).toContain('ingest worker');
  });

  it('tells a stock that nothing is capturing it, and where to go instead', () => {
    const text = emptyReason({
      symbol: 'ITC',
      kind: 'stock',
      feature: 'gamma profile',
      historical: false
    });

    expect(text).toContain('ITC');
    expect(text).toContain('only indices are captured');
    // The point of the sentence: it must not leave the reader waiting.
    expect(text).not.toContain('today yet');
    expect(text).toContain('Open Interest');
  });

  it('explains Historical separately — the archive is the whole story there', () => {
    expect(
      emptyReason({ symbol: 'ITC', kind: 'stock', feature: 'skew', historical: true })
    ).toContain('Historical is index-only');

    expect(emptyReason({ symbol: 'NIFTY', kind: 'index', feature: 'skew', historical: true })).toBe(
      'No session archived for that date.'
    );
  });

  it('treats an unknown symbol as a stock', () => {
    // The catalog may not have loaded yet. Promising an index's "fills in
    // shortly" to something that is not an index is the worse mistake.
    const text = emptyReason({
      symbol: 'WHATEVER',
      kind: undefined,
      feature: 'skew',
      historical: false
    });

    expect(text).toContain('only indices are captured');
  });

  it('names the feature the page could not draw', () => {
    expect(
      emptyReason({ symbol: 'ITC', kind: 'stock', feature: 'premium series', historical: false })
    ).toContain('premium series');
  });
});
