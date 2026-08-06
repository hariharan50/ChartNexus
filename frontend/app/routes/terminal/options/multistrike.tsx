import ComingSoon from '$shared/ui/ComingSoon';
import type { Route } from './+types/multistrike';

export const meta: Route.MetaFunction = () => [{ title: 'MultiStrike Chart · MarketCompass' }];

export default function Multistrike() {
  return (
    <ComingSoon
      title="MultiStrike Chart"
      description="Compare several strikes on a single chart."
    />
  );
}
