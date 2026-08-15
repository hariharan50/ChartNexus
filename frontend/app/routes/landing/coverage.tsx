import { cx } from '$shared/ui/cx';
import { IconCheck, IconCross } from './components/icons';
import { COVERAGE, COVERAGE_MATRIX, LIVE_VS_SOON } from './content';
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

      {/* Instrument matrix — the three indices, their lot sizes and expiry. */}
      <div className={s.section}>
        <div className={s.shell}>
          <div className={s.sectionHead}>
            <p className={s.eyebrow}>Instruments</p>
            <h2 className={s.h2}>Three indices, canonical lots.</h2>
            <p className={s.lead}>
              MarketCompass reads NIFTY, BANKNIFTY and SENSEX options at the nearest expiry. Data is
              mock by default; a Fyers provider can be enabled through backend configuration.
            </p>
          </div>

          <div className={s.specWrap}>
            <table className={s.specTable}>
              <thead>
                <tr>
                  <th scope="col">Index</th>
                  <th scope="col">Lot size</th>
                  <th scope="col">Expiry</th>
                  <th scope="col">Data source</th>
                </tr>
              </thead>
              <tbody>
                {COVERAGE_MATRIX.map((r) => (
                  <tr key={r.index}>
                    <th scope="row">{r.index}</th>
                    <td className="mc-numeric">{r.lot}</td>
                    <td>{r.expiry}</td>
                    <td>{r.source}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Live now vs. honestly-labelled coming-soon — no roadmap promises. */}
      <div className={s.section}>
        <div className={s.shell}>
          <div className={s.sectionHead}>
            <p className={s.eyebrow}>Honest about the edges</p>
            <h2 className={s.h2}>What’s live, and what isn’t — yet.</h2>
            <p className={s.lead}>
              The tools on the left work now. The ones on the right are placeholders labelled
              “coming soon” inside the app; they are not promised here as available.
            </p>
          </div>

          <div className={s.compare}>
            <div className={s.compareCol}>
              <p className={s.compareTitle}>
                Live today
                <span className={cx(s.tag, s.now)}>Working</span>
              </p>
              <ul className={cx(s.compareList, s.yes)}>
                {LIVE_VS_SOON.live.map((item) => (
                  <li key={item}>
                    <IconCheck />
                    {item}
                  </li>
                ))}
              </ul>
            </div>

            <div className={cx(s.compareCol, s.soon)}>
              <p className={s.compareTitle}>
                Not available yet
                <span className={cx(s.tag, s.later)}>Coming soon</span>
              </p>
              <ul className={cx(s.compareList, s.no)}>
                {LIVE_VS_SOON.soon.map((item) => (
                  <li key={item}>
                    <IconCross />
                    {item}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
