import ComingSoon from '$shared/ui/ComingSoon';
import type { Route } from './+types/ai-console';

export const meta: Route.MetaFunction = () => [{ title: 'AI Console · MarketCompass' }];

export default function AiConsole() {
  return (
    <ComingSoon
      title="AI Console"
      description="Ask questions of the live chain and the day's flow in plain language."
    />
  );
}
