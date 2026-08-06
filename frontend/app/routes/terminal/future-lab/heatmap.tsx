import ComingSoon from '$shared/ui/ComingSoon';
import type { Route } from './+types/heatmap';

export const meta: Route.MetaFunction = () => [{ title: 'Future Heatmap · MarketCompass' }];

export default function FutureHeatmap() {
  return (
    <ComingSoon
      title="Future Heatmap"
      description="A heatmap view of futures contracts by price change, volume and OI build-up."
    />
  );
}
