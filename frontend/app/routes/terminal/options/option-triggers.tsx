import ComingSoon from '$shared/ui/ComingSoon';
import type { Route } from './+types/option-triggers';

export const meta: Route.MetaFunction = () => [{ title: 'Option Triggers · ChartNexus' }];

export default function OptionTriggers() {
  return (
    <ComingSoon title="Option Triggers" description="Alerts on notable option-chain events." />
  );
}
