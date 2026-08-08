/**
 * Data for the landing page's demo widgets.
 *
 * Static and deterministic, on purpose. The alternatives both lose:
 *
 *   · Fetching the real endpoints needs a session the visitor does not have,
 *     and would make the front door fail whenever the API is down.
 *   · Adding a QueryClientProvider ships the polling machinery into the app's
 *     lightest route and starts a 15-second poll on a marketing page.
 *
 * Fixtures are zero-network, identical on server and client, and cannot flake
 * a test. Every widget renders a real `DataSourceBadge source="mock"` over the
 * top, so the page demonstrates the provenance guarantee by applying it to
 * itself rather than by describing it.
 *
 * Shaped on tests/e2e/stub-api.mjs so the marketing numbers and the test
 * fixtures are recognisably the same market.
 */

export interface Leg {
  ltp: number;
  oi: number;
  oiChange: number;
  iv: number;
}

export interface Row {
  strike: number;
  ce: Leg;
  pe: Leg;
}

export interface IndexFixture {
  key: string;
  label: string;
  spot: number;
  changePercent: number;
  step: number;
  atm: number;
  rows: Row[];
  maxOi: number;
  pcr: number;
  maxPain: number;
  support: number;
  resistance: number;
  posture: 'Call writers dominant' | 'Put writers dominant' | 'Balanced';
}

const SPOTS = [
  { key: 'NIFTY', label: 'NIFTY 50', spot: 24500.25, changePercent: 0.46, step: 50 },
  { key: 'BANKNIFTY', label: 'BANK NIFTY', spot: 52100.5, changePercent: 0.66, step: 100 },
  { key: 'SENSEX', label: 'SENSEX', spot: 80250.75, changePercent: -0.22, step: 100 }
] as const;

/** Nine strikes either side of ATM, matching the stub's deterministic wobble. */
function build(seed: (typeof SPOTS)[number]): IndexFixture {
  const atm = Math.round(seed.spot / seed.step) * seed.step;
  const rows: Row[] = [];
  let callOiTotal = 0;
  let putOiTotal = 0;

  for (let i = -4; i <= 4; i += 1) {
    const strike = atm + i * seed.step;
    const wobble = ((i + 10) * 37) % 23;
    const callOi = 120_000 + wobble * 5_000 - i * 3_000;
    const putOi = 118_000 + wobble * 4_200 + i * 3_400;
    callOiTotal += callOi;
    putOiTotal += putOi;

    rows.push({
      strike,
      ce: {
        ltp: Math.max(seed.spot - strike, 0) + 60 + wobble,
        oi: callOi,
        oiChange: ((i % 3) - 1) * 4_500 - wobble * 120,
        iv: 13.5 + wobble * 0.11
      },
      pe: {
        ltp: Math.max(strike - seed.spot, 0) + 58 + wobble,
        oi: putOi,
        oiChange: ((i % 4) - 2) * 3_900 + wobble * 95,
        iv: 13.2 + wobble * 0.1
      }
    });
  }

  const maxOi = Math.max(...rows.flatMap((row) => [row.ce.oi, row.pe.oi]));
  const pcr = putOiTotal / callOiTotal;

  // Max pain: the strike where total intrinsic value written is smallest.
  let maxPain = atm;
  let least = Number.POSITIVE_INFINITY;
  for (const candidate of rows) {
    const pain = rows.reduce(
      (total, row) =>
        total +
        Math.max(candidate.strike - row.strike, 0) * row.ce.oi +
        Math.max(row.strike - candidate.strike, 0) * row.pe.oi,
      0
    );
    if (pain < least) {
      least = pain;
      maxPain = candidate.strike;
    }
  }

  // Support is the heaviest put strike below spot, resistance the heaviest call
  // above it — the same reading the terminal's option chain shows.
  const below = rows.filter((row) => row.strike <= seed.spot);
  const above = rows.filter((row) => row.strike >= seed.spot);
  const support = heaviest(below, 'pe') ?? atm;
  const resistance = heaviest(above, 'ce') ?? atm;

  return {
    key: seed.key,
    label: seed.label,
    spot: seed.spot,
    changePercent: seed.changePercent,
    step: seed.step,
    atm,
    rows,
    maxOi,
    pcr,
    maxPain,
    support,
    resistance,
    posture: pcr > 1.05 ? 'Put writers dominant' : pcr < 0.95 ? 'Call writers dominant' : 'Balanced'
  };
}

function heaviest(rows: Row[], side: 'ce' | 'pe'): number | undefined {
  let best: Row | undefined;
  for (const row of rows) {
    if (best === undefined || row[side].oi > best[side].oi) best = row;
  }
  return best?.strike;
}

export const INDICES: IndexFixture[] = SPOTS.map(build);

export function fixtureFor(key: string): IndexFixture {
  // `noUncheckedIndexedAccess` is on, and INDICES is never empty — the fallback
  // is what makes that provable to the compiler rather than asserted.
  return INDICES.find((index) => index.key === key) ?? (INDICES[0] as IndexFixture);
}
