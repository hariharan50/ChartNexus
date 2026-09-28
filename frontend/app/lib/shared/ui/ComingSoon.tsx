import IconClock from './icons/IconClock';
import s from './ComingSoon.module.css';

interface Props {
  title: string;
  description?: string | undefined;
  /**
   * Overrides the pill's wording. Defaults to the phrase every existing
   * placeholder already uses, so naming a different state is opt-in and no
   * page changes wording by accident.
   */
  badge?: string | undefined;
}

export default function ComingSoon({ title, description, badge = 'Coming soon' }: Props) {
  return (
    <section className={s.comingSoon}>
      <div className={s.panel}>
        <span className={s.badge}>
          <span className={s.badgeIco} aria-hidden="true">
            <IconClock />
          </span>
          {badge}
        </span>
        <h1>{title}</h1>
        {description ? <p>{description}</p> : null}
      </div>
    </section>
  );
}
