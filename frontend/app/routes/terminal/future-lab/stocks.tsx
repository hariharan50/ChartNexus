import MoversBoard from './components/MoversBoard';
import type { Route } from './+types/stocks';

export const meta: Route.MetaFunction = () => [{ title: 'Stocks · Future Lab · ChartNexus' }];

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
      subtitle="Every NSE stock with a listed futures contract, against previous close. Pick the contract with the expiry control."
      kind="stock"
      noun="stocks"
      exportName="fno-stocks"
    />
  );
}
