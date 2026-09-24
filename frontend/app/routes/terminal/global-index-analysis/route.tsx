import ComingSoon from '$shared/ui/ComingSoon';
import type { Route } from './+types/route';

export const meta: Route.MetaFunction = () => [{ title: 'Global Index Analysis · MarketCompass' }];

export default function GlobalIndexAnalysis() {
  return (
    <ComingSoon
      title="GIA — Global Index Analysis"
      description="How the world's benchmarks closed, and what they imply for the Indian open."
    />
  );
}
