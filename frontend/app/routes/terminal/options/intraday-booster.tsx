import ComingSoon from '$shared/ui/ComingSoon';
import type { Route } from './+types/intraday-booster';

export const meta: Route.MetaFunction = () => [{ title: 'Intraday Booster · ChartNexus' }];

export default function IntradayBooster() {
  return (
    <ComingSoon
      title="Intraday Booster"
      description="Intraday momentum signals derived from the chain."
    />
  );
}
