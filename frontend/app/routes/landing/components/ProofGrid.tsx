import DataSourceBadge from '$shared/ui/DataSourceBadge';
import { cx } from '$shared/ui/cx';
import { PROOF } from '../copy';
import s from './ProofGrid.module.css';

/**
 * The trust section.
 *
 * A template puts testimonials here. This product has no users yet, and five
 * invented quotes with invented names would be a lie told on the front door of
 * a financial-analytics tool — precisely the kind of thing its provenance
 * guarantee exists to rule out. These are mechanisms instead: each one is
 * something the code does, and each is checkable.
 */
export default function ProofGrid() {
  return (
    <section className={s.section} aria-labelledby="proof-heading">
      <div className={s.inner}>
        <p className={s.eyebrow}>Why you can trust the numbers</p>
        <h2 id="proof-heading" className={s.heading}>
          No testimonials. <strong>Mechanisms.</strong>
        </h2>

        <ul className={s.grid}>
          {PROOF.map((item) => (
            <li key={item.title} className={cx(s.card, 'wide' in item && item.wide && s.wide)}>
              <h3 className={s.title}>{item.title}</h3>
              <p className={s.body}>{item.body}</p>
              {'wide' in item && item.wide ? (
                <span className={s.badgeRow}>
                  <DataSourceBadge source="live" />
                  <DataSourceBadge source="cached" ageSeconds={42} />
                  <DataSourceBadge source="mock" />
                </span>
              ) : null}
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
