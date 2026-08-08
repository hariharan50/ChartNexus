import s from './PillBadge.module.css';

interface Props {
  icon?: React.ReactNode | undefined;
  children: React.ReactNode;
}

/** Rounded-full outline badge that sits above a heading. */
export default function PillBadge({ icon, children }: Props) {
  return (
    <p className={s.badge}>
      {icon ? (
        <span className={s.icon} aria-hidden="true">
          {icon}
        </span>
      ) : null}
      {children}
    </p>
  );
}
