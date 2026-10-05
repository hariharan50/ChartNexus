import ComingSoon from '$shared/ui/ComingSoon';
import type { Route } from './+types/timeseries';

export const meta: Route.MetaFunction = () => [{ title: 'Timeseries · ChartNexus' }];

export default function Timeseries() {
  return (
    <ComingSoon
      title="Timeseries"
      description="Intraday time-series of the key option-chain metrics."
    />
  );
}
