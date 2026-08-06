import ComingSoon from '$shared/ui/ComingSoon';
import type { Route } from './+types/multi-oi-volume';

export const meta: Route.MetaFunction = () => [{ title: 'Multi OI & Volume · MarketCompass' }];

export default function MultiOiVolume() {
  return (
    <ComingSoon
      title="Multi OI &amp; Volume"
      description="Compare open interest and volume across strikes and expiries."
    />
  );
}
