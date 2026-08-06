import ComingSoon from '$shared/ui/ComingSoon';
import type { Route } from './+types/smart-oi';

export const meta: Route.MetaFunction = () => [{ title: 'Smart OI · MarketCompass' }];

export default function SmartOi() {
  return (
    <ComingSoon
      title="Smart OI"
      description="Open-interest shifts filtered down to the moves that matter."
    />
  );
}
