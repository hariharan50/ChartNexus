import ComingSoon from '$shared/ui/ComingSoon';
import type { Route } from './+types/oi-crossover';

export const meta: Route.MetaFunction = () => [{ title: 'OI Crossover · MarketCompass' }];

export default function OiCrossover() {
  return (
    <ComingSoon
      title="OI Crossover"
      description="Strikes where call and put open interest cross."
    />
  );
}
