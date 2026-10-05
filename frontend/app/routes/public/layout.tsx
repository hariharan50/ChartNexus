import type { ComponentType } from 'react';
import { Outlet, useLocation } from 'react-router';
import IconBank from '$shared/ui/icons/IconBank';
import IconBolt from '$shared/ui/icons/IconBolt';
import IconBrain from '$shared/ui/icons/IconBrain';
import IconChart from '$shared/ui/icons/IconChart';
import { cx } from '$shared/ui/cx';
import s from './layout.module.css';

const features: Array<{ icon: ComponentType; title: string; body: string }> = [
  {
    icon: IconChart,
    title: 'Options Intelligence',
    body: 'Live chain analytics, PCR, max pain and OI build-up across NIFTY & SENSEX.'
  },
  {
    icon: IconBrain,
    title: 'AI Signal Engine',
    body: 'Model-driven bias, regime detection and illustrative risk frameworks.'
  },
  {
    icon: IconBank,
    title: 'Institutional Flow',
    body: 'Track FII/DII positioning and smart-money footprints in real time.'
  }
];

export default function PublicLayout() {
  // Re-key the form wrapper per route so React remounts it on each navigation
  // (login ↔ register ↔ forgot-password, and arriving from the landing page).
  // That replays the CSS enter animation instead of snapping in.
  const { pathname } = useLocation();

  return (
    <div className={s.authLayout}>
      {/* Decorative on small screens the panel is hidden entirely, so nothing
          here may carry information the form needs. */}
      <aside className={s.brandPanel}>
        <div className={s.brandInner}>
          <div className={s.wordmark}>
            <span className={s.mark} aria-hidden="true">
              <IconBolt />
            </span>
            <span className={s.name}>ChartNexus</span>
          </div>

          <div className={s.pitch}>
            <h1>
              Analyse Markets.
              <br />
              Trade Smarter.
            </h1>
            <p>
              An AI trading-intelligence terminal for NIFTY 50 and SENSEX — options analytics,
              market regimes and institutional flow in one place.
            </p>
          </div>

          <ul className={s.features}>
            {features.map((feature) => {
              const Icon = feature.icon;
              return (
                <li key={feature.title}>
                  <span className={s.featureIcon} aria-hidden="true">
                    <Icon />
                  </span>
                  <div>
                    <p className={s.featureTitle}>{feature.title}</p>
                    <p className={s.featureBody}>{feature.body}</p>
                  </div>
                </li>
              );
            })}
          </ul>

          <p className={s.disclaimer}>For educational purposes only · Not investment advice</p>
        </div>
      </aside>

      <main className={s.formPanel}>
        <div key={pathname} className={cx(s.formInner, s.pageEnter)}>
          <Outlet />
        </div>
      </main>
    </div>
  );
}
