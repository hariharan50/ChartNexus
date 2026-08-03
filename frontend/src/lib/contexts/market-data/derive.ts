/**
 * Pure mappers: canonical broker contract → dashboard view-models.
 *
 * Everything here is deterministic and side-effect free so it is trivial to
 * unit-test and safe to run inside a Svelte `$derived`. Where the backend does
 * not yet supply a figure (max pain, support/resistance, writing posture, the
 * bias read), it is derived from the option chain with standard options math and
 * clearly interim — no number is invented.
 */

import type { OptionChain, OptionQuote, Quote } from '$contexts/broker-connections/types';
import type {
  AiSummary,
  Bias,
  BuildUp,
  IndexKey,
  IndexQuote,
  OptionRow,
  OptionsMetrics,
  WritingPosture
} from './view-models';

const BACKEND_SYMBOL: Record<IndexKey, string> = {
  NIFTY50: 'NIFTY',
  SENSEX: 'SENSEX',
  BANKNIFTY: 'BANKNIFTY'
};

/** Map a UI index key to the symbol the market API expects. */
export function toBackendSymbol(key: IndexKey): string {
  return BACKEND_SYMBOL[key];
}

/** Parse a Decimal-as-string field to a number (NaN when absent). */
function num(value: string | null | undefined): number {
  return value == null ? NaN : Number.parseFloat(value);
}

/** One index card from its spot quote; a pending card when the quote is absent. */
export function indexCard(key: IndexKey, label: string, quote: Quote | undefined): IndexQuote {
  if (!quote) return { key, label, value: NaN, pending: true };
  const card: IndexQuote = { key, label, value: num(quote.price) };
  if (quote.change_percent != null) card.changePercent = num(quote.change_percent);
  return card;
}

/** INDIA VIX has no feed yet — a placeholder card that reads as "awaiting". */
export function vixCard(): IndexQuote {
  return { key: 'INDIAVIX', label: 'INDIA VIX', value: NaN, pending: true };
}

/**
 * Classify OI build-up from the change in open interest and whether the
 * option's own price is rising. Without a per-strike LTP delta from the broker,
 * price direction is inferred from the underlying: a call gains as the index
 * rises, a put as it falls. Interim, but honest about the inputs it has.
 */
function classifyBuildUp(oiChange: number, priceRising: boolean): BuildUp {
  const oiRising = oiChange > 0;
  if (priceRising && oiRising) return 'Long Build-up';
  if (!priceRising && oiRising) return 'Short Build-up';
  if (priceRising && !oiRising) return 'Short Covering';
  return 'Long Unwinding';
}

function optionRow(
  strike: number,
  type: 'CE' | 'PE',
  atm: boolean,
  q: OptionQuote,
  buildUp: BuildUp
): OptionRow {
  return {
    strike,
    type,
    atm,
    oi: q.oi,
    oiChange: q.oi_change,
    ltp: num(q.ltp),
    iv: q.iv != null ? num(q.iv) : Number.NaN,
    buildUp
  };
}

/** Flatten a canonical chain into PE-then-CE rows, matching the table layout. */
export function optionRows(chain: OptionChain): OptionRow[] {
  const atm = chain.atm_strike != null ? num(chain.atm_strike) : Number.NaN;
  const underlyingRising = (chain.change_percent != null ? num(chain.change_percent) : 0) >= 0;

  const rows: OptionRow[] = [];
  for (const s of chain.strikes) {
    const strike = num(s.strike);
    const isAtm = strike === atm;
    if (s.pe)
      rows.push(
        optionRow(strike, 'PE', isAtm, s.pe, classifyBuildUp(s.pe.oi_change, !underlyingRising))
      );
    if (s.ce)
      rows.push(
        optionRow(strike, 'CE', isAtm, s.ce, classifyBuildUp(s.ce.oi_change, underlyingRising))
      );
  }
  return rows;
}

/** PCR, max pain, support/resistance, and writing posture from the chain. */
export function metrics(chain: OptionChain): OptionsMetrics {
  const rows = chain.strikes.map((s) => ({
    strike: num(s.strike),
    ce: s.ce?.oi ?? 0,
    pe: s.pe?.oi ?? 0
  }));

  const pcr =
    chain.pcr != null ? num(chain.pcr) : chain.total_put_oi / Math.max(1, chain.total_call_oi);

  // Support is the strike carrying the most put OI; resistance the most call OI.
  let support = Number.NaN;
  let resistance = Number.NaN;
  let maxPe = -1;
  let maxCe = -1;
  for (const r of rows) {
    if (r.pe > maxPe) {
      maxPe = r.pe;
      support = r.strike;
    }
    if (r.ce > maxCe) {
      maxCe = r.ce;
      resistance = r.strike;
    }
  }

  // Max pain: the expiry level minimising the intrinsic value owed to holders.
  let maxPain = Number.NaN;
  let least = Number.POSITIVE_INFINITY;
  for (const expiry of rows) {
    let pain = 0;
    for (const r of rows) {
      pain += r.ce * Math.max(0, expiry.strike - r.strike);
      pain += r.pe * Math.max(0, r.strike - expiry.strike);
    }
    if (pain < least) {
      least = pain;
      maxPain = expiry.strike;
    }
  }

  const writingPosture: WritingPosture =
    pcr >= 1.1 ? 'PUT_WRITERS_DOMINANT' : pcr <= 0.9 ? 'CALL_WRITERS_DOMINANT' : 'BALANCED';

  return { pcr, maxPain, support, resistance, writingPosture };
}

function biasOf(changePercent: number | undefined): Bias {
  if (changePercent == null || Number.isNaN(changePercent)) return 'Neutral';
  if (changePercent > 0.1) return 'Bullish';
  if (changePercent < -0.1) return 'Bearish';
  return 'Neutral';
}

/** A rule-based summary from the real change % and chain metrics (interim). */
export function aiSummary(indices: IndexQuote[], m: OptionsMetrics): AiSummary {
  const biases = indices
    .filter((i) => i.key !== 'INDIAVIX')
    .map((i) => ({ label: i.label, bias: biasOf(i.changePercent) }));
  return { biases, pcr: m.pcr, support: m.support, resistance: m.resistance };
}
