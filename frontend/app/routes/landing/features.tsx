import { cx } from '$shared/ui/cx';
import { Icon, IconCheck, IconLock } from './components/icons';
import { FEATURES, MODULE_DETAILS } from './content';
import s from './route.module.css';
import type { Route } from './+types/features';

export const meta: Route.MetaFunction = () => [
  { title: 'Features · ChartNexus' },
  {
    name: 'description',
    content:
      'Option chain, PCR & max pain, OI build-up, gamma and vega exposure, the ATM straddle, and ' +
      'provenance on every number.'
  }
];

export default function Features() {
  return (
    <section className={s.pageIntro}>
      <div className={s.shell}>
        <div className={s.sectionHead}>
          <p className={s.eyebrow}>What you get</p>
          <h1 className={s.h2}>Everything the chain says, already worked out.</h1>
          <p className={s.lead}>
            ChartNexus is built for reading NSE options — chain structure, positioning, and the
            greeks that move the premium — not for placing orders. Every module runs on mock data by
            default and labels its own provenance.
          </p>
        </div>

        <div className={cx(s.grid, s.gridFeatures)}>
          {FEATURES.map((feature) => (
            <article key={feature.title} className={s.card}>
              <span className={s.tile}>
                <Icon name={feature.glyph} />
              </span>
              <h3 className={s.cardTitle}>{feature.title}</h3>
              <p className={s.cardBody}>{feature.body}</p>
            </article>
          ))}
        </div>
      </div>

      {/* Deep-dive: each live module, one paragraph plus the concrete things it
          draws on screen. */}
      <div className={s.section}>
        <div className={s.shell}>
          <div className={s.sectionHead}>
            <p className={s.eyebrow}>Module by module</p>
            <h2 className={s.h2}>What each tool actually puts on screen.</h2>
            <p className={s.lead}>
              No mystery numbers. Every module below is live today on mock data, and each figure
              carries its own provenance stamp.
            </p>
          </div>

          <div className={s.deepGrid}>
            {MODULE_DETAILS.map((mod) => (
              <article key={mod.title} className={s.deepRow}>
                <div>
                  <div className={s.deepHead}>
                    <span className={s.tile}>
                      <Icon name={mod.glyph} />
                    </span>
                    <h3>{mod.title}</h3>
                  </div>
                  <p className={s.deepBody}>{mod.body}</p>
                </div>
                <ul className={s.deepPoints}>
                  {mod.points.map((point) => (
                    <li key={point}>
                      <IconCheck />
                      {point}
                    </li>
                  ))}
                </ul>
              </article>
            ))}
          </div>
        </div>
      </div>

      {/* Provenance callout — the promise that ties every module together. */}
      <div className={s.section}>
        <div className={s.shell}>
          <div className={s.callout}>
            <span className={s.calloutIcon}>
              <IconLock />
            </span>
            <div>
              <h3>Provenance on every number</h3>
              <p>
                Each figure declares whether it is live, cached, last-good or simulated — and how
                old it is. Degraded data is labelled, never hidden, so a stale number can never pass
                for a fresh one.
              </p>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
