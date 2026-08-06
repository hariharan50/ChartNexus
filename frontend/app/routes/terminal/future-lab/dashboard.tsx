import ComingSoon from '$shared/ui/ComingSoon';
import type { Route } from './+types/dashboard';

export const meta: Route.MetaFunction = () => [{ title: 'Future Dashboard · MarketCompass' }];

export default function FutureDashboard() {
  return (
    <ComingSoon
      title="Future Dashboard"
      description="A live overview of futures pricing, basis, and rollover across NIFTY, BANKNIFTY and SENSEX."
    />
  );
}
