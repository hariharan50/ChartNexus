import ComingSoon from '$shared/ui/ComingSoon';
import type { Route } from './+types/price-vs-oi';

export const meta: Route.MetaFunction = () => [{ title: 'Price vs OI · MarketCompass' }];

export default function FuturePriceVsOi() {
  return (
    <ComingSoon
      title="Price vs OI"
      description="Futures price movement plotted against open-interest build-up and unwinding."
    />
  );
}
