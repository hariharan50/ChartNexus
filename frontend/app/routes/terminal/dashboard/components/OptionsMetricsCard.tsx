import { formatInt } from '$shared/formatting/numbers';
import { cx } from '$shared/ui/cx';
import IconTarget from '$shared/ui/icons/IconTarget';
import type { OptionsMetrics } from '../dashboard-data';
import s from './OptionsMetricsCard.module.css';
import Panel from './Panel';

interface Props {
  metrics: OptionsMetrics;
}

export default function OptionsMetricsCard({ metrics }: Props) {
  const postureLabel = metrics.writingPosture.replaceAll('_', ' ');

  return (
    <Panel title="Options Metrics" icon={<IconTarget />}>
      <dl className={s.grid}>
        <div className={s.cell}>
          <dt>PCR (OI)</dt>
          <dd className="cn-numeric">{metrics.pcr.toFixed(2)}</dd>
        </div>
        <div className={s.cell}>
          <dt>Max Pain</dt>
          <dd className="cn-numeric">{formatInt(metrics.maxPain)}</dd>
        </div>
        <div className={s.cell}>
          <dt>Support</dt>
          <dd className={cx('cn-numeric', s.support)}>{formatInt(metrics.support)}</dd>
        </div>
        <div className={s.cell}>
          <dt>Resistance</dt>
          <dd className={cx('cn-numeric', s.resistance)}>{formatInt(metrics.resistance)}</dd>
        </div>
      </dl>

      <div className={s.posture}>
        <dt>Writing Posture</dt>
        <dd>{postureLabel}</dd>
      </div>
    </Panel>
  );
}
