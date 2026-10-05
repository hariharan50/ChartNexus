import { cx } from '$shared/ui/cx';
import { Icon } from './components/icons';
import { GUARANTEES, PROVENANCE_LEGEND, SCOPE } from './content';
import s from './route.module.css';
import type { Route } from './+types/scope';

export const meta: Route.MetaFunction = () => [
  { title: 'Scope · ChartNexus' },
  {
    name: 'description',
    content:
      'The current ChartNexus scope: instruments, market data, a read-only design, and ' +
      'provenance built into every response.'
  }
];

export default function Scope() {
  return (
    <section className={s.pageIntro}>
      <div className={s.shell}>
        <div className={s.sectionHead}>
          <p className={s.eyebrow}>Current scope</p>
          <h1 className={s.h2}>What you’re actually getting.</h1>
          <p className={s.lead}>
            Read this before you sign up, not after. The current scope is Phase-1 analytics on mock
            market data by default, with Fyers integration paths for configured environments.
          </p>
        </div>

        <div className={cx(s.grid, s.grid2)}>
          {SCOPE.map((item) => (
            <article key={item.title} className={s.card}>
              <h3 className={s.plainTitle}>{item.title}</h3>
              <p className={s.cardBody}>{item.body}</p>
            </article>
          ))}
        </div>
      </div>

      {/* Read-only guarantees — the boundaries, stated plainly. */}
      <div className={s.section}>
        <div className={s.shell}>
          <div className={s.sectionHead}>
            <p className={s.eyebrow}>Read-only by design</p>
            <h2 className={s.h2}>Four things it will never do.</h2>
            <p className={s.lead}>
              These are not policies that could change — they are the shape of the app. There is no
              code path to an order book and no wallet to hold funds.
            </p>
          </div>

          <div className={cx(s.grid, s.grid2)}>
            {GUARANTEES.map((g) => (
              <article key={g.title} className={s.card}>
                <span className={s.tile}>
                  <Icon name={g.glyph} />
                </span>
                <h3 className={s.cardTitle}>{g.title}</h3>
                <p className={s.cardBody}>{g.body}</p>
              </article>
            ))}
          </div>
        </div>
      </div>

      {/* Provenance spec — the four states every number can carry. */}
      <div className={s.section}>
        <div className={s.shell}>
          <div className={s.sectionHead}>
            <p className={s.eyebrow}>Provenance built in</p>
            <h2 className={s.h2}>Every number tells you where it came from.</h2>
          </div>

          <div className={s.legend}>
            {PROVENANCE_LEGEND.map((p) => (
              <div key={p.label} className={s.legendItem}>
                <span className={cx(s.legendChip, s[p.tone])}>{p.label}</span>
                <p className={s.legendMeaning}>{p.meaning}</p>
              </div>
            ))}
          </div>

          <p className={s.disclaimer}>
            ChartNexus is an analytics tool for informational use only. It is not investment advice
            and is not a SEBI-registered advisory service. Nothing here is a recommendation to buy
            or sell any instrument.
          </p>
        </div>
      </div>
    </section>
  );
}
