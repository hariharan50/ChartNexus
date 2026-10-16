import { create } from 'zustand';
import { DEFAULT_INSTRUMENT } from '$shared/config/instruments';

const SYMBOL_KEY = 'cn-pref-instrument';

interface InstrumentState {
  /** The last instrument the reader chose, or the default before they have. */
  symbol: string;
  init: () => void;
  setSymbol: (symbol: string) => void;
}

/**
 * The instrument the terminal is looking at, remembered between visits.
 *
 * Every analytics page used to own this as `useState(0)` over a hardcoded
 * three, so walking from Open Interest to Max Pain silently put you back on
 * NIFTY. One store means a choice survives the walk, and the reload after it.
 *
 * The URL still outranks this — see `useSelectedInstrument`. A link someone
 * sends must open on the symbol they meant, not on whatever the recipient
 * happened to look at last.
 *
 * See the SSR-singleton note in theme-store.ts: never set from render.
 */
export const useInstrumentStore = create<InstrumentState>()((set) => ({
  symbol: DEFAULT_INSTRUMENT,

  init: () => {
    if (typeof document === 'undefined') return;
    const stored = localStorage.getItem(SYMBOL_KEY)?.trim().toUpperCase();
    // A symbol that has left the F&O list is not worth guarding against here:
    // the catalog is not loaded yet at init time, and a stale ticker shows the
    // page's own "nothing for that" state rather than a wrong chart.
    if (stored) set({ symbol: stored });
  },

  setSymbol: (symbol) => {
    const value = symbol.trim().toUpperCase();
    if (!value) return;
    set({ symbol: value });
    if (typeof document === 'undefined') return;
    localStorage.setItem(SYMBOL_KEY, value);
  }
}));
