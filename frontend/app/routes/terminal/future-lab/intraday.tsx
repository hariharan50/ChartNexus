import ComingSoon from '$shared/ui/ComingSoon';
import type { Route } from './+types/intraday';

export const meta: Route.MetaFunction = () => [{ title: 'Future Intraday · MarketCompass' }];

export default function FutureIntraday() {
  return (
    <ComingSoon
      title="Future Intraday"
      description="Intraday price and volume chart for the active futures contract."
    />
  );
}
