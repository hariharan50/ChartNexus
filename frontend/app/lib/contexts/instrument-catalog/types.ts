/** Wire shapes for `GET /api/v1/instruments`. */

export type InstrumentKind = 'index' | 'stock';

/**
 * One tradeable F&O underlying, as the catalog describes it.
 *
 * This replaces the hand-written three-entry arrays that used to be copied
 * into every page. The list is served from the backend catalog, which refreshes
 * daily from the exchange symbol master — so a stock joining or leaving the
 * F&O list needs no frontend change at all.
 */
export interface Instrument {
  symbol: string;
  kind: InstrumentKind;
  name: string;
  exchange: string;
  lot_size: number;
  tick_size: string;
  strike_step: string | null;
  isin: string | null;
  sector: string | null;
  /**
   * Tracked indices this instrument belongs to, e.g. ['NIFTY50'].
   *
   * Optional because an API predating the field simply omits it. Typed that
   * way deliberately: treating it as always-present is what let
   * `for (const i of entry.indices)` reach production and take the page down
   * with "undefined is not iterable".
   */
  indices?: string[];
}

export interface InstrumentList {
  instruments: Instrument[];
  count: number;
}
