import { describe, expect, it } from 'vitest';
import { PANELS } from '../../app/routes/terminal/future-lab/dashboard-data';

/**
 * The Future Dashboard lays these out as a fixed three-column grid, so the
 * shape of this list *is* the layout: three `up` panels then three `down` ones
 * fill the two rows. A seventh panel, or a flipped tone, would leave a ragged
 * row with nothing to catch it.
 */
describe('dashboard panels', () => {
  it('fills two rows of three', () => {
    expect(PANELS).toHaveLength(6);
  });

  it('groups every rising state into the first row and every falling one into the second', () => {
    const tones = PANELS.map((panel) => panel.tone);

    expect(tones).toEqual(['up', 'up', 'up', 'down', 'down', 'down']);
  });

  it('leads each row with the price movers going that way', () => {
    expect(PANELS[0]?.key).toBe('top_gainers');
    expect(PANELS[3]?.key).toBe('top_losers');
  });

  it('keeps the four build-up states, one per row position', () => {
    const buildup = PANELS.filter(
      (panel) => panel.key !== 'top_gainers' && panel.key !== 'top_losers'
    );

    expect(buildup.map((panel) => panel.key)).toEqual([
      'long_buildup',
      'short_covering',
      'short_buildup',
      'long_unwinding'
    ]);
  });

  it('names every panel', () => {
    for (const panel of PANELS) {
      expect(panel.title.length).toBeGreaterThan(0);
    }
  });
});
