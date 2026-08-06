import ComingSoon from '$shared/ui/ComingSoon';
import type { Route } from './+types/premium-decay';

export const meta: Route.MetaFunction = () => [{ title: 'Premium Decay · MarketCompass' }];

export default function PremiumDecay() {
  return (
    <ComingSoon
      title="Premium Decay"
      description="Theta decay of option premium over the session."
    />
  );
}
