import MoversBoard from './components/MoversBoard';
import type { Route } from './+types/market-movers';

export const meta: Route.MetaFunction = () => [
  { title: 'Market Movers · Future Lab · MarketCompass' }
];

/**
 * The whole F&O board — index contracts and single names together.
 *
 * Deliberately wider than the Stocks page rather than a second copy of it:
 * "what is moving" is a question about the market, and answering it without
 * NIFTY or BANKNIFTY would be a strange omission. Everything else — the
 * filters, the build-up legend, the heatmap, the rail — is the same component.
 */
export default function MarketMovers() {
  return (
    <MoversBoard
      title="Live Future Market Movers"
      subtitle="NSE futures top gainers & losers — front-month contracts, against previous close."
      noun="contracts"
      exportName="fno-movers"
    />
  );
}
