import ComingSoon from '$shared/ui/ComingSoon';
import type { Route } from './+types/volatility-skew';

export const meta: Route.MetaFunction = () => [{ title: 'Volatility Skew · MarketCompass' }];

export default function VolatilitySkew() {
  return (
    <ComingSoon title="Volatility Skew" description="Implied volatility across the strike range." />
  );
}
