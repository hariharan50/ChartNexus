import ComingSoon from '$shared/ui/ComingSoon';
import type { Route } from './+types/iv-hv';

export const meta: Route.MetaFunction = () => [{ title: 'IV - HV · MarketCompass' }];

export default function IvHv() {
  return (
    <ComingSoon
      title="IV - HV"
      description="The spread between implied and historical volatility."
    />
  );
}
