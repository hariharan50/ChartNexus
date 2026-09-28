import ComingSoon from '$shared/ui/ComingSoon';
import type { Route } from './+types/route';

export const meta: Route.MetaFunction = () => [
  { title: 'PMS — Pre Market Screener · MarketCompass' }
];

/**
 * PMS — the pre-market screener.
 *
 * A placeholder with a route and a nav entry, and nothing behind it yet. It
 * exists as its own directory rather than a flat file because the screener is
 * expected to grow the usual set of neighbours - components, a data module -
 * and moving a page later churns the route config and every link to it.
 */
export default function PreMarketScreener() {
  return (
    <ComingSoon
      badge="Under development"
      title="PMS — Pre Market Screener"
      description="Screen the F&O universe before the open."
    />
  );
}
