import ComingSoon from '$shared/ui/ComingSoon';
import type { Route } from './+types/max-pain';

export const meta: Route.MetaFunction = () => [{ title: 'Max Pain · MarketCompass' }];

export default function MaxPain() {
  return (
    <ComingSoon
      title="Max Pain"
      description="The expiry level that minimises option-holder payout, over time."
    />
  );
}
