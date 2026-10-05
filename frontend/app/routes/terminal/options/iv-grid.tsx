import ComingSoon from '$shared/ui/ComingSoon';
import type { Route } from './+types/iv-grid';

export const meta: Route.MetaFunction = () => [{ title: 'IV Grid · ChartNexus' }];

export default function IvGrid() {
  return (
    <ComingSoon
      title="IV Grid"
      description="Implied volatility across the strike and expiry grid."
    />
  );
}
