import MoversBoard from './components/MoversBoard';
import type { Route } from './+types/stocks';

export const meta: Route.MetaFunction = () => [{ title: 'Stocks · Future Lab · MarketCompass' }];

/**
 * Every F&O stock, ranked and classified.
 *
 * The same board as Market Movers, narrowed to single names — the index
 * contracts are excluded server-side via `kind=stock`, so the row count is the
 * real stock universe rather than "everything minus nine".
 */
export default function Stocks() {
  return (
    <MoversBoard
      title="Live Future Market Movers — Stocks"
      subtitle="Every NSE stock with a listed futures contract — front-month, against previous close."
      kind="stock"
      noun="stocks"
      exportName="fno-stocks"
    />
  );
}
