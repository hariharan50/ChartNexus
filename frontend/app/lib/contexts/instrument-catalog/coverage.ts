/**
 * What the terminal actually has for a given instrument, and how to say so.
 *
 * Options Lab analytics come from two places. Every request makes a **live**
 * broker call for the current chain, so per-strike OI, PCR and max pain work
 * for any contract in the catalog. The intraday shape of those numbers comes
 * from an **archive** the ingest worker fills — and that worker captures
 * indices only (`entrypoints/ingest_runtime.py`, `ingest_symbols`).
 *
 * So a stock is not uniformly thin, and saying "no data" would be as wrong as
 * showing a blank chart: Open Interest and PCR are real for ITC right now,
 * while Gamma Exposure cannot be computed at all without captures. The pages
 * already branch on `data_quality === 'empty'`; this is the sentence they say
 * when they do, so a reader learns the shape of the gap instead of waiting for
 * numbers that are never coming.
 */

import { useInstruments } from './queries';
import type { InstrumentKind } from './types';

/** The pages that work for any instrument, for pointing a reader at them. */
const LIVE_CAPABLE = 'Open Interest, Put-Call Ratio, Max Pain and Multi OI & Volume';

export interface EmptyReasonInput {
  symbol: string;
  /** From the catalog. Unknown symbols are treated as stocks — the cautious way. */
  kind: InstrumentKind | undefined;
  /** What this page calls the thing it could not draw, e.g. 'gamma profile'. */
  feature: string;
  /** Historical mode asks the archive directly, so it fails for a different reason. */
  historical: boolean;
}

/**
 * Why a panel is empty, in one sentence.
 *
 * Indices keep the original wording: for them an empty panel really does mean
 * "the worker has not got there yet today", and it will fill in.
 */
export function emptyReason({ symbol, kind, feature, historical }: EmptyReasonInput): string {
  const isStock = kind !== 'index';

  if (historical) {
    return isStock
      ? `No archived sessions for ${symbol} — only index chains are captured, so Historical is index-only.`
      : 'No session archived for that date.';
  }

  if (isStock) {
    return (
      `The ${feature} is built from captured chain snapshots, and only indices are captured — ` +
      `so there is none for ${symbol}. Its live chain still works: see ${LIVE_CAPABLE}.`
    );
  }

  return `No ${feature} recorded for today yet — it fills in as the ingest worker captures the chain.`;
}

/**
 * `emptyReason`, with the instrument's kind read from the cached catalog.
 *
 * The catalog is one session-cached fetch, so this costs nothing beyond what
 * the picker on the same page already pays.
 */
export function useEmptyReason(symbol: string, feature: string, historical: boolean): string {
  const { instruments } = useInstruments();
  const kind = instruments.find((row) => row.symbol === symbol)?.kind;
  return emptyReason({ symbol, kind, feature, historical });
}
