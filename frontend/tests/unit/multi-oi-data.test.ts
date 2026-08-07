import { describe, expect, it } from 'vitest';
import {
  contractLabel,
  metricValues,
  peMinusCe,
  topByLatest,
  type ContractSeries
} from '../../app/routes/terminal/options/multi-oi-volume/multi-oi-data';

/**
 * The derivations behind Multi OI & Volume.
 *
 * The endpoint sends raw `oi` and `volume`; everything the three charts plot is
 * worked out here, so these are the arithmetic that would silently draw a wrong
 * line rather than fail.
 */

function contract(
  id: string,
  option_type: 'CE' | 'PE',
  oi: (number | null)[],
  volume: (number | null)[] = []
): ContractSeries {
  return {
    id,
    strike: Number.parseInt(id, 10),
    option_type,
    oi,
    volume: volume.length ? volume : oi.map(() => 0)
  };
}

describe('metricValues', () => {
  it('returns open interest unchanged', () => {
    expect(metricValues(contract('24600CE', 'CE', [100, 150, 220]), 'oi')).toEqual([100, 150, 220]);
  });

  it('derives change from the session open at index 0', () => {
    // Not transmitted: point 0 is the open, so this is `oi[i] - oi[0]` — the
    // same derivation the Open Interest page makes. A second array would be a
    // second source of truth for a figure both pages have to agree on.
    expect(metricValues(contract('24600CE', 'CE', [100, 150, 220]), 'change')).toEqual([
      0, 50, 120
    ]);
  });

  it('reports a fall as a negative change', () => {
    expect(metricValues(contract('24600CE', 'CE', [500, 400, 300]), 'change')).toEqual([
      0, -100, -200
    ]);
  });

  it('returns volume unchanged', () => {
    const c = contract('24600CE', 'CE', [1, 2], [10, 40]);
    expect(metricValues(c, 'volume')).toEqual([10, 40]);
  });

  it('survives an empty series', () => {
    expect(metricValues(contract('24600CE', 'CE', []), 'change')).toEqual([]);
  });

  it('leaves a leg null until it is first quoted', () => {
    // A strike listed part-way through the morning was not quoted at the open;
    // zero would draw it along the axis and then leap.
    const c = contract('24600CE', 'CE', [null, null, 100, 160]);
    expect(metricValues(c, 'oi')).toEqual([null, null, 100, 160]);
    // Index 0 is null, so the baseline falls back to 0 and the change series
    // reads the raw level from the leg's first quote onward.
    expect(metricValues(c, 'change')).toEqual([null, null, 100, 160]);
  });
});

describe('topByLatest', () => {
  const contracts = [
    contract('24600CE', 'CE', [10, 300], [0, 5]),
    contract('24650CE', 'CE', [10, 100], [0, 900]),
    contract('24700PE', 'PE', [10, 500], [0, 50])
  ];

  it('ranks by the latest reading, biggest first', () => {
    expect(topByLatest(contracts, 'oi', 2)).toEqual(['24700PE', '24600CE']);
  });

  it('ranks volume independently of open interest', () => {
    expect(topByLatest(contracts, 'volume', 1)).toEqual(['24650CE']);
  });

  it('settles ties on the id so a refetch cannot reshuffle the colours', () => {
    // Selection order assigns the palette, so an unstable sort would repaint
    // every line on a poll that changed nothing.
    const tied = [contract('24700CE', 'CE', [1, 50]), contract('24600CE', 'CE', [1, 50])];
    expect(topByLatest(tied, 'oi', 2)).toEqual(['24600CE', '24700CE']);
  });

  it('asks for more than exist without complaint', () => {
    expect(topByLatest(contracts, 'oi', 99)).toHaveLength(3);
  });
});

describe('peMinusCe', () => {
  it('nets put writing against call writing', () => {
    // Positive means puts are building faster than calls — support forming.
    const net = peMinusCe([
      contract('24600PE', 'PE', [100, 300]), // +200
      contract('24700CE', 'CE', [100, 150]) // +50
    ]);
    expect(net).toEqual([0, 150]);
  });

  it('goes negative when calls are written harder', () => {
    const net = peMinusCe([
      contract('24600PE', 'PE', [100, 120]), // +20
      contract('24700CE', 'CE', [100, 400]) // +300
    ]);
    expect(net).toEqual([0, -280]);
  });

  it('is empty when nothing is selected', () => {
    expect(peMinusCe([])).toEqual([]);
  });
});

describe('contractLabel', () => {
  it('reads as a strike and a side', () => {
    expect(contractLabel(contract('24700CE', 'CE', [1]))).toBe('24700 CE');
  });
});
