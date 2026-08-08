import { cx } from '$shared/ui/cx';
import { TRUST } from '../copy';
import s from './TrustBar.module.css';

/**
 * Where a template would put download counts and a star rating. The product has
 * neither, so these are four facts that can be checked by clicking through it.
 */
export default function TrustBar() {
  return (
    <section className={s.bar} aria-label="At a glance">
      <ul className={s.list}>
        {TRUST.map((item) => (
          <li key={item.label} className={s.item}>
            <span className={cx(s.value, 'mc-numeric')}>{item.value}</span>
            <span className={s.label}>{item.label}</span>
            <span className={s.detail}>{item.detail}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
