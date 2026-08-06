import ComingSoon from '$shared/ui/ComingSoon';
import type { Route } from './+types/market-movers';

export const meta: Route.MetaFunction = () => [{ title: 'Market Movers · MarketCompass' }];

export default function MarketMovers() {
  return (
    <ComingSoon
      title="Market Movers"
      description="The futures contracts moving the most today, ranked by price change and volume."
    />
  );
}
