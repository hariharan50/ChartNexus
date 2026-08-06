import ComingSoon from '$shared/ui/ComingSoon';
import type { Route } from './+types/sentiment-cycle';

export const meta: Route.MetaFunction = () => [{ title: 'Future Sentiment Cycle · MarketCompass' }];

export default function SentimentCycle() {
  return (
    <ComingSoon
      title="Future Sentiment Cycle"
      description="Where futures positioning sits in the long build-up / short-covering cycle."
    />
  );
}
