import ComingSoon from '$shared/ui/ComingSoon';
import type { Route } from './+types/pcr';

export const meta: Route.MetaFunction = () => [{ title: 'Put-Call Ratio · MarketCompass' }];

export default function Pcr() {
  return (
    <ComingSoon
      title="Put-Call Ratio"
      description="Track the put/call ratio by OI and volume through the session."
    />
  );
}
