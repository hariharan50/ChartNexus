import ComingSoon from '$shared/ui/ComingSoon';
import type { Route } from './+types/pe-ce-difference';

export const meta: Route.MetaFunction = () => [{ title: 'PE-CE Difference · MarketCompass' }];

export default function PeCeDifference() {
  return (
    <ComingSoon
      title="PE-CE Difference"
      description="Net put-minus-call open interest across the chain."
    />
  );
}
