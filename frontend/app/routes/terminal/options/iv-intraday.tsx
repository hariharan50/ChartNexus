import ComingSoon from '$shared/ui/ComingSoon';
import type { Route } from './+types/iv-intraday';

export const meta: Route.MetaFunction = () => [{ title: 'IV - Intraday · MarketCompass' }];

export default function IvIntraday() {
  return (
    <ComingSoon title="IV - Intraday" description="Intraday movement of implied volatility." />
  );
}
