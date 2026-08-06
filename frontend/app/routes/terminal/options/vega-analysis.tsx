import ComingSoon from '$shared/ui/ComingSoon';
import type { Route } from './+types/vega-analysis';

export const meta: Route.MetaFunction = () => [{ title: 'Vega Analysis · MarketCompass' }];

export default function VegaAnalysis() {
  return (
    <ComingSoon
      title="Vega Analysis"
      description="Volatility exposure across strikes and expiries."
    />
  );
}
