import { Link } from 'react-router';
import { cx } from '$shared/ui/cx';
import s from './CtaLink.module.css';

interface Props {
  to: string;
  tone?: 'solid' | 'ghost' | undefined;
  size?: 'md' | 'lg' | undefined;
  className?: string | undefined;
  children: React.ReactNode;
}

/**
 * A call to action. Deliberately not `$shared/ui/Button`.
 *
 * Every CTA on this page navigates, so the correct element is an anchor, not a
 * `<button>` — and `Button` is a button at `--mc-radius` (6px) and
 * `--mc-control-h` (40px), neither of which is the pill this design asks for or
 * the 44px touch target it needs. Reskinning it would have meant a `variant`
 * that only one page uses.
 */
export default function CtaLink({ to, tone = 'solid', size = 'md', className, children }: Props) {
  return (
    <Link
      to={to}
      className={cx(s.cta, tone === 'solid' ? s.solid : s.ghost, size === 'lg' && s.lg, className)}
    >
      {children}
    </Link>
  );
}
