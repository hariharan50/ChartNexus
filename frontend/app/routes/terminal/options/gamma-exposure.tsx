import ComingSoon from '$shared/ui/ComingSoon';
import type { Route } from './+types/gamma-exposure';

export const meta: Route.MetaFunction = () => [{ title: 'Gamma Exposure · MarketCompass' }];

export default function GammaExposure() {
  return (
    <ComingSoon
      title="Gamma Exposure"
      description="Dealer gamma positioning and its pin and repel zones."
    />
  );
}
