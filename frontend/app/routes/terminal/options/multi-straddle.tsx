import ComingSoon from '$shared/ui/ComingSoon';
import type { Route } from './+types/multi-straddle';

export const meta: Route.MetaFunction = () => [{ title: 'Multi-Straddle Chart · MarketCompass' }];

export default function MultiStraddle() {
  return (
    <ComingSoon
      title="Multi-Straddle Chart"
      description="Straddle prices across multiple strikes."
    />
  );
}
