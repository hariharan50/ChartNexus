import IconClock from './icons/IconClock';
import s from './ComingSoon.module.css';

interface Props {
  title: string;
  description?: string | undefined;
}

export default function ComingSoon({ title, description }: Props) {
  return (
    <section className={s.comingSoon}>
      <div className={s.panel}>
        <span className={s.badge}>
          <span className={s.badgeIco} aria-hidden="true">
            <IconClock />
          </span>
          Coming soon
        </span>
        <h1>{title}</h1>
        {description ? <p>{description}</p> : null}
      </div>
    </section>
  );
}
