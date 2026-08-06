import ComingSoon from '$shared/ui/ComingSoon';
import type { Route } from './+types/iv-hv-ivp';

export const meta: Route.MetaFunction = () => [{ title: 'IV/HV/IVP Chart · MarketCompass' }];

export default function IvHvIvp() {
  return (
    <ComingSoon
      title="IV/HV/IVP Chart"
      description="Implied vs historical volatility and IV percentile."
    />
  );
}
