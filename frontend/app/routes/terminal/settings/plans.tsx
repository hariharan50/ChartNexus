import s from './plans.module.css';
import type { Route } from './+types/plans';

export const meta: Route.MetaFunction = () => [{ title: 'My Plans · Settings · ChartNexus' }];

export default function SettingsPlans() {
  return (
    <>
      <h1 className={s.title}>My Plans</h1>

      <div className={s.planState}>
        <div className={s.planCopy}>
          <p className={s.planName}>Free plan</p>
          <p className={s.planDesc}>
            Full access to the live terminal — option chain, PCR, max pain and OI build-up.
          </p>
        </div>
        <span className={s.badge}>Current</span>
      </div>

      <p className={s.note}>
        Billing isn’t live yet. Paid tiers with higher limits and team seats are on the way — you’ll
        be able to upgrade from here when they land.
      </p>
    </>
  );
}
