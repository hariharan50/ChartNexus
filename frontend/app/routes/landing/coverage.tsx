import { cx } from '$shared/ui/cx';
import { COVERAGE } from './content';
import s from './route.module.css';
import type { Route } from './+types/coverage';

export const meta: Route.MetaFunction = () => [
  { title: 'Coverage · MarketCompass' },
  {
    name: 'description',
    content:
      'The MarketCompass tools that are live today: option chain, open interest, PCR, max pain, ' +
      'gamma exposure, vega analysis and the ATM straddle.'
  }
];

export default function Coverage() {
  return (
    <section className={s.pageIntro}>
      <div className={s.shell}>
        <div className={s.sectionHead}>
          <p className={s.eyebrow}>What you can read today</p>
          <h1 className={s.h2}>The tools that are live, not a roadmap.</h1>
          <p className={s.lead}>
            These modules work right now, on mock data, before you connect anything. The rest of the
            Options Lab and Future Lab are honestly labelled “coming soon” inside the app rather
            than promised here.
          </p>
        </div>

        <div className={s.rows}>
          {COVERAGE.map((label, i) => (
            <div key={label} className={s.row}>
              <span className={cx(s.rowNum, 'mc-numeric')}>{i + 1}</span>
              <span className={s.rowLabel}>{label}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
