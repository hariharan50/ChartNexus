import type { BuildUp } from '$contexts/market-data/view-models';
import { cx } from '$shared/ui/cx';
import s from './BuildupBadge.module.css';

interface Props {
  buildup?: BuildUp | undefined;
}

// Arrow + short code + tone for each build-up label. Longs sit on the deeper
// shade of their colour, unwinding/covering on the brighter one.
const MAP: Record<BuildUp, { arrow: string; code: string; tone: string }> = {
  'Short Covering': { arrow: '↑', code: 'SC', tone: 'sc' },
  'Long Build-up': { arrow: '↗', code: 'L', tone: 'l' },
  'Short Build-up': { arrow: '↘', code: 'S', tone: 's' },
  'Long Unwinding': { arrow: '↓', code: 'LU', tone: 'lu' }
};

export default function BuildupBadge({ buildup }: Props) {
  const info = buildup ? MAP[buildup] : undefined;

  if (!info) {
    return <span className={cx(s.badge, s.none)}>—</span>;
  }

  return (
    <span className={cx(s.badge, s[info.tone])} title={buildup}>
      <span aria-hidden="true">{info.arrow}</span> {info.code}
    </span>
  );
}
