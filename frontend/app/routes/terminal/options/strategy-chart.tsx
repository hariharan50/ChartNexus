import ComingSoon from '$shared/ui/ComingSoon';
import type { Route } from './+types/strategy-chart';

export const meta: Route.MetaFunction = () => [{ title: 'Strategy Chart · ChartNexus' }];

export default function StrategyChart() {
  return (
    <ComingSoon
      title="Strategy Chart"
      description="Build and visualise multi-leg option strategies."
    />
  );
}
