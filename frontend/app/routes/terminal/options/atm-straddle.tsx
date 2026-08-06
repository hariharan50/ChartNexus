import ComingSoon from '$shared/ui/ComingSoon';
import type { Route } from './+types/atm-straddle';

export const meta: Route.MetaFunction = () => [{ title: 'ATM Straddle Chart · MarketCompass' }];

export default function AtmStraddle() {
  return (
    <ComingSoon
      title="ATM Straddle Chart"
      description="The at-the-money straddle price through the day."
    />
  );
}
