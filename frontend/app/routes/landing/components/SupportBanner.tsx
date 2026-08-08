import { Link } from 'react-router';
import IconMessage from '$shared/ui/icons/IconMessage';
import { SUPPORT } from '../copy';
import s from './SupportBanner.module.css';

export default function SupportBanner() {
  return (
    <section className={s.section}>
      <div className={s.banner}>
        <span className={s.icon} aria-hidden="true">
          <IconMessage />
        </span>
        <div className={s.text}>
          <h2 className={s.heading}>{SUPPORT.heading}</h2>
          <p className={s.body}>{SUPPORT.body}</p>
        </div>
        <Link className={s.cta} to={SUPPORT.cta.to}>
          {SUPPORT.cta.label}
        </Link>
      </div>
    </section>
  );
}
